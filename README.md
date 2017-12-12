This is a glue script that reads information from the C3TT [1] and talks to voctoweb [2], youtube [3] and twitter [4].

It publishes recordings an handles all necessary steps like thumbnail generation

## Dependencies
### Debian / Ubuntu
```
sudo apt-get install python3 python3-requests python3-pip ffmpeg
sudo pip3 install paramiko configparser twitter pillow
```

## Usage
Use the provided client.conf.example in the docs directory to tell the script to which hosts it should talk. 
Most of the configuration is done in the tracker via properties and passed to the script in the ticket.

## License
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"Viel Spaß am Gerät"


* [1] TBA (the tracker will be publicly available soon)
* [2] https://github.com/voc/voctoweb
* [3] https://www.youtube.com/yt/dev/de/api-resources.html
* [4] https://dev.twitter.com/rest/public
