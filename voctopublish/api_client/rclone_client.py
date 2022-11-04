import logging
from datetime import datetime
from os.path import join
from subprocess import CalledProcessError, check_output

from model.ticket_module import Ticket

logging = logging.getLogger(__name__)


class RCloneClient:
    def __init__(self, t: Ticket, config):
        self.ticket = t
        self.rclone_path = config.get("rclone", "exe_path")
        self.rclone_config = config.get("rclone", "config_path")

        date_time = datetime.strptime(t.date, "%Y-%m-%dT%H:%M:%S%z")
        self.destination = self.ticket.rclone_destination.format(
            day=date_time.strftime("%d"),
            event=self.acronym,
            fahrplan_day=self.ticket.day,
            filename_full=self.ticket.filename,
            filename_guid=f"{self.ticket.guid}.{self.ticket.profile_extension}",
            filename_short=self.ticket.local_filename,
            month=date_time.strftime("%m"),
            year=date_time.strftime("%Y"),
        )

    def upload(self):
        try:
            out = check_output(
                [
                    self.rclone_path,
                    "--config",
                    self.rclone_config,
                    "--verbose",
                    "--error-on-no-transfer",
                    "copyto",
                    join(self.ticket.publishing_path, self.ticket.local_filename),
                    self.destination,
                ]
            )
            for line in out.decode().splitlines():
                logging.debug(line)
        except CalledProcessError as e:
            if e.returncode == 9:
                logging.warn(f"rclone reported no transferred files (return code 9)!")
            else:
                logging.error(f"rclone exited {e.returncode}!")
            for line in e.stdout.decode().splitlines():
                logging.error(f"STDOUT: {line}")
            for line in e.stderr.decode().splitlines():
                logging.error(f"STDERR: {line}")
            return e.returncode
        else:
            logging.info(f"uploaded to {self.destination}")
            return 0
