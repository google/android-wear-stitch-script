This is not an official Google product.

This script generates stitched-together screenshots of Android Wear UIs that
are too tall to fit on the screen all at once. It does by taking a screenshot,
scrolling a bit, taking another screenshot etc. until it reaches the bottom
of the screen. It then does some image processing to merge the screenshots
that were taken.

This works with real devices and with emulated watches.

Usage: wear_screenshot_stitch.py [-h] [--out-dir OUT_DIR]
                                 [--file-prefix FILE_PREFIX | --file-name FILE_NAME]
                                 [--adb-args ADB_ARGS]
                                 [--capture] | [--no-capture]
                                 [--round] | [--square]
                                 [--transparency] | [--no-transparency]
                                 [--inter-capture-delay INTER_CAPTURE_DELAY]
                                 [--keep-captures] | [--no-keep-captures]
                                 [--max-captures MAX_CAPTURES]

Take Wear screenshots using adb and stitch them together

optional arguments:
  -h, --help            show this help message and exit
  --out-dir OUT_DIR     The dirctory to output to. (default: the current
                        directory)
  --file-prefix FILE_PREFIX
                        The file prefix to use. An auto-incrementing index is
                        added to generate the full filename so the previous
                        captures are not overwritten. Mutually exclusive with
                        --file-name. (default: stitch)
  --file-name FILE_NAME
                        The name of the output file. This file will be
                        overwritten. Mutually exclusive with --file-prefix.
  --adb-args ADB_ARGS   Arguments for adb. Use quotes to keep arguments
                        together. Bare flags should have a space. E.g.
                        wear_screenshot_stitch.py --round --adb-args " -e"

Capture options:
  --capture             Capture new images to stitch. Contrast with --no-
                        capture. (default)
  --no-capture          Do not capture new images, just try to stitch existing
                        images. Contrast with --capture.
  --round               Set capture type for round displays, framing the
                        stitched image with round borders. Contrast with
                        --square. (default)
  --square              Set capture type for square displays, framing the
                        stitched image with square borders. Contrast with
                        --round
  --transparency        Use alpha transparency for pixels around the corners
                        of the output that the round screen chops off
  --no-transparency     Disable transparency
  --inter-capture-delay INTER_CAPTURE_DELAY
                        How long to wait between captures, in ms, i.e. to give
                        enought time for the scrollbar to disappear. (default:
                        1000)
  --keep-captures       Keep the intermediary captured screens. Contrast with
                        --no-keep-captures.
  --no-keep-captures    Discard the intermediary captured screens. Contrast
                        with --keep-captures. (default)
  --max-captures MAX_CAPTURES
                        The maximum number of screens to capture. (default:
                        50)
