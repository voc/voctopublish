#!/bin/bash

# Fail completely if there is an error in one of the steps
set -e

BASEDIR=$(dirname $0)
INTERVAL=180

file="$1"
# target output directory, optional
outdir="$2"
# thumbnail output filename, relative to outdir, optional
thumb_filename="$3"
# poster image output filename, relative to outdir, optional
poster_filename="$4"


LENGTH=$(ffprobe -loglevel quiet -print_format default -show_format "$file" | grep duration= | sed -e 's/duration=\([[:digit:]]*\).*/\1/g')

TMPDIR=$(mktemp -d /tmp/thumb.XXXXXX)

if [ -n "$thumb_filename" ] || [ -n "$poster_filename" ]; then
  outjpg=${outdir}/${thumb_filename}
  outjpg_preview=${outdir}/${poster_filename}
elif [ -z "$outdir" ]; then
  outjpg=${file%.*}.jpg
  outjpg_preview=${file%.*}_preview.jpg
else
  outjpg=${outdir}/$(basename "${file%.*}.jpg")
  outjpg_preview=${outdir}/$(basename "${file%.*}_preview.jpg")
fi

# Make sure potential subdirs in the image directory also exist
mkdir -p `dirname "$outjpg"`
mkdir -p `dirname "$outjpg_preview"`


# now extract candidates and convert to non-anamorphic images
#
# we use equidistant sampling, but skip parts of the file that might contain pre-/postroles
# also, use higher resolution sampling at the beginning, as there's usually some interesting stuff there


for POS in 20 30 40 $(seq 15 $INTERVAL $[ $LENGTH - 60 ])
do
	ffmpeg -loglevel error -ss $POS -i "$file"  -an -r 1 -filter:v 'scale=sar*iw:ih' -vframes 1 -f image2 -pix_fmt yuv420p -vcodec png -y "$TMPDIR/$POS.png"
done

WINNER=$(python3 $BASEDIR/select.py $TMPDIR/*.png)
# lanczos scaling algorithm produces a sharper image for small sizes than the default choice
# set pix_fmt to create a be more compatible output, otherwise the input format would would be kept
ffmpeg -loglevel error -i $WINNER -filter_complex:v 'scale=400:-1:lanczos' -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y "$outjpg"
ffmpeg -loglevel error -i $WINNER                                          -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y "$outjpg_preview"

rm -rf $TMPDIR || true
