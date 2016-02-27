This repository contains a glue script that reads information from the C3TT [1] and talks to media.ccc.de [2], youtube [3] and twitter [4].

It publishes recordings an handles all neccessary steps like thumbnail generation

== Decencies
Debian / Ubuntu
sudo apt-get install python3 python3-requests python3-pip python3-setuptools ffmpeg
sudo pip-3 install paramiko twitter

== Usage
use the provided client.conf.example to tell the script to which hosts it should talk. Most of the configuration is done in the tracker

[1] TBA (the tracker will be publicly available soon
[2] https://github.com/voc/media.ccc.de
[3] https://www.youtube.com/yt/dev/de/api-resources.html
[4] https://dev.twitter.com/rest/public


"Viel Spaß am Gerät"
