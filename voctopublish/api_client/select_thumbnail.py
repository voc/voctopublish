#!/usr/bin/python3
#    Copyright (C) 2017  Florian Larysch, derpeter
#    Florian Larysch <fl@n621.de>
#    derpeter derpeter@berlin.ccc.de
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import math
import operator

from PIL import Image, ImageStat


# see http://dx.doi.org/10.1109/ICMT.2011.6002001 for algorithms

def luminance_score(hist):
    i1 = int(len(hist) / 5)
    i2 = int(len(hist) * 4 / 5)

    t1 = 0.7
    t2 = 0.8

    base_score = 1.0

    hist_sum = sum(hist) * base_score
    lower = sum(hist[:i1]) * base_score
    upper = sum(hist[i2:]) * base_score

    if lower / hist_sum <= t1:
        return -lower / hist_sum
    elif upper / hist_sum <= t2:
        return -upper / hist_sum
    else:
        return -1.0


def luminance_diversity(hist):
    avg = sum(hist) / len(hist)
    max_num = max(hist)

    if max_num == 0:
        return -1.0

    return -1.0 + 1.0 * math.sqrt(
        sum(map(lambda x: (x - avg) ** 2, hist))
    ) / max_num


def luminance_variance(stat):
    n = stat.count[0]
    sum2 = stat.sum2[0]
    sum_ = stat.sum[0]
    avg = sum_ / n

    return -1 + math.sqrt(sum2 + n * avg ** 2 - 2 * avg * sum_) / 255.0


def calc_score(path):
    img = Image.open(path)
    gray = img.convert(mode="L")
    gray_hist = gray.histogram()
    stat = ImageStat.Stat(gray)

    s3 = luminance_score(gray_hist)
    s4 = luminance_diversity(gray_hist)
    s7 = luminance_variance(stat)

    return s3 + s4 + s7


# scores = {}
#
# verbose = 0
# if sys.argv[1] == "-v":
#     verbose = 1
#     sys.argv.pop(1)
#
# for f in sys.argv[1:]:
#     score = calc_score(f)
#
#     scores[f] = score
#
# sorted_scores = sorted(scores.items(), key=operator.itemgetter(1), reverse=True)
#
# if verbose == 1:
#     print("scores:")
#
#     for (f, score) in sorted_scores:
#         print("%10s: %f" % (f, score))
#
# else:
#     print(sorted_scores[0][0])
