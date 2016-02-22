#!/bin/bash

BASEDIR=$(dirname $0)
INTERVAL=180

INPUT="$1"
LENGTH=$(ffprobe -loglevel quiet -print_format default -show_format "$INPUT" | grep duration= | sed -e 's/duration=\([[:digit:]]*\).*/\1/g')

# now extract candidates and convert to non-anamorphic images
#
# we use equidistant sampling, but skip parts of the file that might contain pre-/postroles
# also, use higher resolution sampling at the beginning, as there's usually some interesting stuff there

for i in 20 30 40 $(seq 15 $INTERVAL $[ $LENGTH - 60 ])
do
	POS=$[ $RANDOM % $LENGTH ]
	ffmpeg -loglevel error -ss $POS -i "$INPUT"  -an -r 1 -filter:v 'scale=sar*iw:ih' -vframes 1 -f image2 -vcodec mjpeg -y $POS.jpg
done

WINNER=$(python2 $BASEDIR/select.py *.jpg)

mv "$WINNER" winner.jpg

ffmpeg -loglevel error -i winner.jpg -filter:v 'crop=ih*4/3:ih' -s 192x144 thumb.jpg
