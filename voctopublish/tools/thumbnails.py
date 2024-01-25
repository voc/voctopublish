#    Copyright (C) 2018  derpeter
#    Copyright (C) 2021  kunsi
#    derpeter@berlin.ccc.de
#    voc@kunsmann.eu
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

import logging
from operator import itemgetter
from os.path import isfile, join
from shutil import move
from subprocess import CalledProcessError, check_output
from tempfile import TemporaryDirectory

from model.ticket_module import Ticket
from tools.select_thumbnail import calc_score


class ThumbnailGenerator:
    def __init__(self, ticket, config):
        self.ticket = ticket
        self.config = config

    @property
    def path(self):
        if self.ticket.thumbnail_file:
            return self.ticket.thumbnail_file
        else:
            return join(
                self.ticket.publishing_path,
                str(self.ticket.fahrplan_id) + "-thumbnail.png",
            )

    @property
    def exists(self):
        return isfile(self.path)

    def generate(self):
        if self.exists:
            raise ThumbnailException("generate() called, but thumbnail already exists!")

        if self.ticket.thumbnail_file:
            # don't ever try to override a custom thumbnail
            raise FileNotFoundError(self.path)

        source = join(self.ticket.publishing_path, self.ticket.local_filename)
        logging.info("generating thumbs for " + source)

        try:
            r = check_output(
                "ffprobe -print_format flat -show_format -loglevel quiet "
                + source
                + ' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ',
                shell=True,
            )
        except Exception as e_:
            raise ThumbnailException(
                "ERROR: could not get duration " + r.decode("utf-8")
            ) from e_

        length = int(r.decode())

        with TemporaryDirectory() as tmpdir:
            logging.debug("TemporaryDirectory is " + str(tmpdir))

            # now extract candidates and convert to non-anamorphic images
            # we use equidistant sampling, but skip parts of the file that
            # might contain pre-/postroles
            # also, use higher resolution sampling at the beginning, as
            # there's usually some interesting stuff there

            if length > 20:
                scores = {}
                interval = 180
                candidates = [20, 30, 40]  # some fixed candidates we always want to hit
                logging.debug(
                    "length of video used for thumbnail generation " + str(length)
                )
                candidates.extend(
                    list(range(15, length - 60, interval))
                )  # pick some more candidates based on the file length
                try:
                    for pos in candidates:
                        candidate = join(tmpdir, str(pos) + ".png")
                        r = check_output(
                            "ffmpeg -loglevel error -ss "
                            + str(pos)
                            + " -i "
                            + source
                            + ' -an -r 1 -filter:v "scale=sar*iw:ih" -vframes 1 -f image2 -pix_fmt yuv420p -vcodec png -y '
                            + candidate,
                            shell=True,
                        )
                        if isfile(candidate):
                            scores[candidate] = calc_score(candidate)
                        else:
                            logging.warning(
                                "ffmpeg was not able to create candidat for "
                                + str(candidate)
                            )
                except CalledProcessError as e_:
                    raise ThumbnailException(
                        "ffmpeg exited with the following error, while extracting candidates for thumbnails. "
                        + e_.output.decode("utf-8")
                    ) from e_
                except Exception as e_:
                    raise ThumbnailException(
                        "Could not extract candidates: " + str(r)
                    ) from e_

                sorted_scores = sorted(scores.items(), key=itemgetter(1), reverse=True)
                winner = sorted_scores[0][0]
                logging.debug("Winner: " + winner)

                move(winner, self.path)
            else:
                try:
                    r = check_output(
                        "ffmpeg -loglevel error -i "
                        + source
                        + ' -an -r 1 -filter:v "scale=sar*iw:ih" -vframes 1 -f image2 -pix_fmt yuv420p -vcodec png -y '
                        + self.path,
                        shell=True,
                    )
                except Exception as e_:
                    raise ThumbnailException from e_

            logging.info("thumbnails generated")


class ThumbnailException(Exception):
    pass
