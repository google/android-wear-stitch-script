#!/usr/bin/python
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

Detailed usage:

./wear_screenshot_stitch.py [--square] [--transparency] [--adb-args ...]

    --square                assume device has a square screen
                            (otherwise a circular screen will be assumed)

    --transparency          use alpha transparency for pixels around the corners
                            of the output that the circular screen chops off

    --adb-args              any arguments following this will passed to
                            adb directly

"""

import hashlib
import math
import os
import os.path
import subprocess
import sys
import time

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
  print "Executing adb command: " + cmd
  subprocess.call(cmd, shell=True)


def rgb_to_int(x):
  """Converts an rgb/rgba tuple into an int"""
  r = x[0]
  g = x[1]
  b = x[2]
  return (r * 0x10000) + (g * 0x100) + b


def get_row_hashes(image_id):
  """Returns a list of hashes, one per row in the image.

  Each hash represents the contents of the middle of the row.
  """

  im = Image.open("screencaps/{}.png".format(image_id))
  row_hashes = []
  (width, height) = im.size

  # A simple hash function, using the pixel values as coefficients
  # of a polynomial. Note: we only use data from the middle of the row,
  # as on a circular screen, left and right edges get cut off.
  for y in range(height):
    row_hash = 1
    for x in range(int(width * 0.3), int(width * 0.7)):
      row_hash *= HASH_MULTIPLIER
      row_hash += rgb_to_int(im.getpixel((x, y)))
      row_hash %= HASH_MODULO
    row_hashes.append(row_hash)
  return row_hashes


def main(skip_capture, circular, transparency, adb_args=""):
  """Captures screenshots using adb and stitches them together."""

  if not os.path.exists("screencaps"):
    os.mkdir("screencaps")
  else:
    if not skip_capture:
      subprocess.call("rm screencaps/*.png", shell=True)

  # Limit the max number of screenshots captured in case the tool never
  # reaches the bottom (e.g. for an infinitely scrollable list).
  image_count = 50

  if not skip_capture:
    # Capture screenshots from the device, sending a small swipe gesture after each.
    # Stop when we get two identical screenshots in a row (this indicates that we're
    # at the bottom of the UI) or we hit the iteration limit.
    old_md5sum = ""
    for i in range(image_count):
      print "Capturing image {}".format(i)
      adb(adb_args, "shell screencap -p /sdcard/{}.png".format(i))
      adb(adb_args, "shell input swipe 50 200 50 100")
      adb(adb_args, "pull /sdcard/{}.png screencaps/".format(i))
      if not os.path.exists("screencaps/{}.png".format(i)):
        print FAIL + "Failed to capture screenshot. Is your device connected?" + ENDC
        return

      md5sum = hashlib.md5(
          open("screencaps/{}.png".format(i), "rb").read()).hexdigest()

      if md5sum == old_md5sum:
        image_count = i
        break
      old_md5sum = md5sum
      time.sleep(1)  # Give time for scrollbar to disappear

  # Examine the first image that was captured.
  im = Image.open("screencaps/0.png")
  (width, height) = im.size

  rows_for_absolute = defaultdict(list)
  previous_row_hashes = get_row_hashes(0)
  absolute_offset = 0

  for y in range(len(previous_row_hashes)):
    rows_for_absolute[y].append((0, y))

  # For each subsequent image that was captured, find the y-offset at which it's
  # the closest match to the previous image.
  for i in range(1, image_count):
    row_hashes = get_row_hashes(i)

    (best_score, best_offset) = max([(len([
        z for z in range(0, height - offset)
        if row_hashes[z] == previous_row_hashes[z + offset]
    ]), offset) for offset in range(0, height)])
    print "Match for image {} - ({}, {})".format(i, best_score, best_offset)

    absolute_offset += best_offset
    for y in range(height):
      rows_for_absolute[y + absolute_offset].append((i, y))

    previous_row_hashes = row_hashes

  # Create an output image by overlaying each of the images captured at the
  # offsets we worked out earlier.
  output_height = max(rows_for_absolute.keys()) + 1
  print("Producting an image with height {}".format(output_height))
  im_out = Image.new("RGBA", (width, output_height))
  middle = (height - 1) / 2.0
  for y in range(output_height):
    on_screen_pixels = defaultdict(list)
    off_screen_pixels = defaultdict(list)
    for (image_id, row) in rows_for_absolute[y]:
      im = Image.open("screencaps/{}.png".format(image_id))
      for x in range(width):
        if circular:
          hypot_squared = \
            (((x - middle) ** 2) + ((row - middle) ** 2))
          on_screen = hypot_squared < ((height / 2.0) - 2)**2
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
          if transparency:
            suggested_pixel = (0, 0, 0, 0)  # transparency
          else:
            (_, suggested_pixel) = min((math.fabs(row - middle), p)
                                       for (row, p) in off_screen_pixels[x])
      else:
        (_, suggested_pixel) = min((math.fabs(row - middle), p)
                                   for (row, p) in on_screen_pixels[x])
      im_out.putpixel((x, y), suggested_pixel)

  # And we're done! Let the user know where to find the output image.
  output_filename = "screencaps/output.png"
  im_out.save(output_filename)
  print "\n" + OKBLUE + "Wrote {}".format(output_filename) + ENDC


if __name__ == "__main__":
  adb_args = ""
  if "--adb-args" in sys.argv:
    adb_args = sys.argv[sys.argv.index("--adb-args") + 1]

  main(
      skip_capture="--skip-capture" in sys.argv[1:],
      circular=not "--square" in sys.argv[1:],
      transparency="--transparency" in sys.argv[1:],
      adb_args=adb_args)
