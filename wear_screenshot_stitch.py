#!/usr/bin/env python

# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A tool that takes Wear screenshots using adb and stitches them together.

See README for instructions.
"""

from __future__ import division
from __future__ import print_function

import hashlib
import math
import os
import os.path
import subprocess
import sys
import time
import argparse

from collections import defaultdict
from PIL import Image

HASH_MODULO = 2**64
HASH_MULTIPLIER = 31

# Control codes for changing the colour of the text output to the terminal
FAIL = "\033[91m"
OKBLUE = "\033[94m"
ENDC = "\033[0m"


def adb(adb_args, command):
  """Runs an adb command, discarding the result."""
  cmd = "adb {} {}".format(adb_args, command)
  print("Executing adb command: " + cmd)
  subprocess.call(cmd, shell=True)


def rgb_to_int(x):
  """Converts an rgb/rgba tuple into an int"""
  r = x[0]
  g = x[1]
  b = x[2]
  return (r * 0x10000) + (g * 0x100) + b


def get_row_hashes(capture_file):
  """Returns a list of hashes, one per row in the image.

  Each hash represents the contents of the middle of the row.
  """

  im = Image.open(capture_file)
  row_hashes = []
  (width, height) = im.size

  # A simple hash function, using the pixel values as coefficients
  # of a polynomial. Note: we only use data from the middle of the row,
  # as on a round screen, left and right edges get cut off.
  for y in range(height):
    row_hash = 1
    for x in range(int(width * 0.3), int(width * 0.7)):
      row_hash *= HASH_MULTIPLIER
      row_hash += rgb_to_int(im.getpixel((x, y)))
      row_hash %= HASH_MODULO
    row_hashes.append(row_hash)
  return row_hashes

def padded_index(max, num):
  index_chars = int(math.ceil(math.log10(max)))
  index_format = '{{:0{}d}}'.format(index_chars)
  return index_format.format(num)

def find_next_file_name(dir, file_base, max):
  base = os.path.join(dir, file_base)
  for i in range(max):
    index = padded_index(max, i)
    name = "{}{}.png".format(base, index)
    if not os.path.exists(name):
      return name
  raise RuntimeError("Too many captures in directory. Could not generate filename.")

def find_num_captures(dir, file_prefix, max_captures):
  next_capture = find_next_file_name(dir, file_prefix, max_captures)
  index = os.path.splitext(next_capture)[0].rsplit('_', 1)[-1]
  return int(index)

def setup_files(out_dir, prefix, name, capture, max_captures):
  if not os.path.exists(out_dir):
    if capture:
      os.mkdir(out_dir)
    else:
      raise RuntimeError('Capture directory does not exist. Cannot stitch.')
  if name is not None:
    out_file = os.path.join(out_dir, name)
  else:
    if capture:
      out_file = find_next_file_name(out_dir, prefix, 1000)
    else:
      raise RuntimeError('Must specify file-name in no-capture mode')

  basepath, _ = os.path.splitext(out_file)
  basename = os.path.basename(basepath)

  if (not basepath or not basename):
    raise ValueError('Invalid path, prefix, or file provided: {}, {}, {}'.format(out_dir, prefix, name))

  capture_file_prefix = "{}_".format(basename)
  capture_file_path = os.path.dirname(basepath)

  if capture:
    num_files = max_captures
  else:
    num_files = find_num_captures(capture_file_path, capture_file_prefix, max_captures)

  return out_file, capture_file_path, capture_file_prefix, num_files

def get_capture_file_path(path, prefix, max, num):
  return '{}{}.png'.format(os.path.join(path, prefix), padded_index(max, num))

def rm_captures(path, prefix):
  subprocess.call("rm {}*.png".format(os.path.join(path, prefix)), shell=True)

def main(args):
  """Captures screenshots using adb and stitches them together."""

  out_file, cap_dir, cap_file_prefix, image_count = \
      setup_files(args.out_dir, args.file_prefix, args.file_name, args.capture, args.max_captures)

  if args.capture:
    rm_captures(cap_dir, cap_file_prefix)

  if args.capture:
    # Capture screenshots from the device, sending a small swipe gesture after each.
    # Stop when we get two identical screenshots in a row (this indicates that we're
    # at the bottom of the UI) or we hit the iteration limit.
    old_md5sum = ""
    for i in range(image_count):
      index = padded_index(args.max_captures, i)
      cap_file = get_capture_file_path(cap_dir, cap_file_prefix, args.max_captures, i)
      print("Capturing image {}".format(i))
      adb(args.adb_args, "shell screencap -p /sdcard/{}.png".format(index))
      adb(args.adb_args, "shell input swipe 50 200 50 100")
      adb(args.adb_args, "pull /sdcard/{}.png {}".format(index, cap_file))
      if not os.path.exists(cap_file):
        print(FAIL + "Failed to capture screenshot. Is your device connected?" + ENDC)
        return

      md5sum = hashlib.md5(
          open(cap_file, "rb").read()).hexdigest()

      if md5sum == old_md5sum:
        image_count = i
        break
      old_md5sum = md5sum
      time.sleep(args.inter_capture_delay / 1000)  # Give time for scrollbar to disappear

  # Examine the first image that was captured.
  im = Image.open(get_capture_file_path(cap_dir, cap_file_prefix, args.max_captures, 0))
  (width, height) = im.size

  rows_for_absolute = defaultdict(list)
  previous_row_hashes = get_row_hashes(
    get_capture_file_path(cap_dir, cap_file_prefix, args.max_captures, 0))
  absolute_offset = 0

  for y in range(len(previous_row_hashes)):
    rows_for_absolute[y].append((0, y))

  # For each subsequent image that was captured, find the y-offset at which it's
  # the closest match to the previous image.
  for i in range(1, image_count):
    row_hashes = get_row_hashes(
      get_capture_file_path(cap_dir, cap_file_prefix, args.max_captures, i))

    (best_score, best_offset) = max([(len([
        z for z in range(0, height - offset)
        if row_hashes[z] == previous_row_hashes[z + offset]
    ]), offset) for offset in range(0, height)])
    print("Match for image {} - ({}, {})".format(i, best_score, best_offset))

    absolute_offset += best_offset
    for y in range(height):
      rows_for_absolute[y + absolute_offset].append((i, y))

    previous_row_hashes = row_hashes

  # Create an output image by overlaying each of the images captured at the
  # offsets we worked out earlier.
  output_height = max(rows_for_absolute.keys()) + 1
  print("Producting an image with height {}".format(output_height))
  im_out = Image.new("RGBA", (width, output_height))
  middle = (height - 1) / 2
  for y in range(output_height):
    on_screen_pixels = defaultdict(list)
    off_screen_pixels = defaultdict(list)
    for (image_id, row) in rows_for_absolute[y]:
      im = Image.open(get_capture_file_path(cap_dir, cap_file_prefix, args.max_captures, image_id))
      for x in range(width):
        if args.round:
          hypot_squared = \
            (((x - middle) ** 2) + ((row - middle) ** 2))
          on_screen = hypot_squared < ((height / 2) - 2)**2
        else:
          on_screen = True
        p = im.getpixel((x, row))

        if on_screen:
          on_screen_pixels[x].append((row, p))
        else:
          off_screen_pixels[x].append((row, p))

    # For each pixel, we try to work out the most suitable color value for it
    # in the final stitched image.
    for x in range(width):
      if not on_screen_pixels[x]:
        if y >= height / 2 and y < (output_height - height / 2):
          suggested_pixel = im_out.getpixel((x, y - 2))
        else:
          if args.transparency:
            suggested_pixel = (0, 0, 0, 0)  # transparency
          else:
            (_, suggested_pixel) = min((math.fabs(row - middle), p)
                                       for (row, p) in off_screen_pixels[x])
      else:
        (_, suggested_pixel) = min((math.fabs(row - middle), p)
                                   for (row, p) in on_screen_pixels[x])
      im_out.putpixel((x, y), suggested_pixel)

  # And we're done! Let the user know where to find the output image.
  im_out.save(out_file)
  print("\n" + OKBLUE + "Wrote {}".format(out_file) + ENDC)
  if not args.keep_captures:
    rm_captures(cap_dir, cap_file_prefix)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Take Wear screenshots using adb and stitch them together')
  parser.add_argument('--out-dir', default='.',
                      help='The dirctory to output to. (default: the current directory)')
  group = parser.add_mutually_exclusive_group()
  group.add_argument('--file-prefix', default='stitch',
                      help='The file prefix to use. An auto-incrementing index is added to generate the full filename so the previous captures are not overwritten. Mutually exclusive with --file-name. (default: stitch)')
  group.add_argument('--file-name',
                     help='The name of the output file. This file will be overwritten. Mutually exclusive with --file-prefix.')

  parser.add_argument('--adb-args', default='',
                      help='Arguments for adb. Use quotes to keep arguments together. Bare flags should have a space. E.g. {} --round --adb-args " -e"'.format(os.path.basename(__file__)))

  group = parser.add_argument_group('Capture options')
  group.add_argument('--capture', dest='capture', action='store_true', default=True,
                      help='Capture new images to stitch. Contrast with --no-capture. (default)')
  group.add_argument('--no-capture', dest='capture', action='store_false',
                      help='Do not capture new images, just try to stitch existing images. Contrast with --capture.')
  group.add_argument('--round', dest='round', action='store_true', default=True,
                      help='Set capture type for round displays, framing the stitched image with round borders. Contrast with --square. (default)')
  group.add_argument('--square', dest='round', action='store_false',
                      help='Set capture type for square displays, framing the stitched image with square borders. Contrast with --round')
  group.add_argument('--transparency', dest='transparency', action='store_true', default=False,
                      help='Use alpha transparency for pixels around the corners of the output that the round screen chops off')
  group.add_argument('--no-transparency', dest='transparency', action='store_false',
                      help='Disable transparency')
  group.add_argument('--inter-capture-delay', type=int, default=1000,
                      help='How long to wait between captures, in ms, i.e. to give enought time for the scrollbar to disappear. (default: 1000)')
  group.add_argument('--keep-captures', dest='keep_captures', action='store_true', default=False,
                      help='Keep the intermediary captured screens. Contrast with --no-keep-captures.')
  group.add_argument('--no-keep-captures', dest='keep_captures', action='store_false',
                      help='Discard the intermediary captured screens. Contrast with --keep-captures. (default)')
  group.add_argument('--max-captures', type=int, default=50,
                      help='The maximum number of screens to capture. (default: 50)')

  args = parser.parse_args()

  main(args)
