#!/usr/bin/python3
#    Copyright (C) 2014  derpeter
#    derpeter@berlin.ccc.de
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

# Call like this:
#     try:
#         youtubeUrls = publish_youtube(ticket, config['youtube']['secret'])
#         for i, youtubeUrl in enumerate(youtubeUrls):
#             setTicketProperties(ticket_id, {'YouTube.Url'+str(i): youtubeUrl}, url, group, host, secret)
#     except RuntimeError as err:
#         setTicketFailed(ticket_id, "Publishing failed: \n" + str(err), url, group, host, secret)
#         logging.error("Publishing failed: \n" + str(err))
#         sys.exit(-1)

from html.parser import HTMLParser
import subprocess, logging, requests, json, mimetypes, os, re
logger = logging.getLogger()

# publish a file on youtube
def publish_youtube(ticket, clientId, clientSecret):
    logger.info("publishing Ticket %s (%s) to youtube" % (ticket['Fahrplan.ID'], ticket['Fahrplan.Title']))

    if not 'Publishing.YouTube.Token' in ticket:
        raise RuntimeError('Property "Publishing.YouTube.Token" missing in ticket - did you set the YouTube-Properties on the Project?')

    accessToken = getFreshToken(ticket['Publishing.YouTube.Token'], clientId, clientSecret)
    channelId = getChannelId(accessToken)

    infile = str(ticket['Publishing.Path']) + str(ticket['Fahrplan.ID']) + "-" +ticket['EncodingProfile.Slug'] + "." + ticket['EncodingProfile.Extension']

    # if a second language is configured, remux the video to only have the one audio track and upload it twice
    m = re.match('(..)-(..)', ticket['Record.Language'])
    if m:
        logger.debug('remuxing dual-language video into two parts')

        outfile1 = str(ticket['Publishing.Path']) + str(ticket['Fahrplan.ID']) + "-" +ticket['EncodingProfile.Slug'] + "-audio1." + ticket['EncodingProfile.Extension']
        outfile2 = str(ticket['Publishing.Path']) + str(ticket['Fahrplan.ID']) + "-" +ticket['EncodingProfile.Slug'] + "-audio2." + ticket['EncodingProfile.Extension']
        youtubeUrls = []

        logger.debug('remuxing with original audio to '+outfile1)
        ticket['Publishing.Infile'] = outfile1

        if subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', infile, '-map', '0:0', '-map', '0:1', '-c', 'copy', outfile1]) != 0:
            raise RuntimeError('error remuxing '+infile+' to '+outfile1)

        videoId = uploadVideo(ticket, accessToken, channelId)
        youtubeUrls.append('https://www.youtube.com/watch?v='+videoId)

        logger.debug('remuxing with translated audio to '+outfile2)
        ticket['Publishing.Infile'] = outfile2
        ticket['Publishing.InfileIsTranslated'] = m.group(2)
        if subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', infile, '-map', '0:0', '-map', '0:2', '-c', 'copy', outfile2]) != 0:
            raise RuntimeError('error remuxing '+infile+' to '+outfile2)

        videoId = uploadVideo(ticket, accessToken, channelId)
        youtubeUrls.append('https://www.youtube.com/watch?v='+videoId)

        logger.info("deleting remuxed versions: %s and %s" % (outfile1, outfile2))
        os.remove(outfile1)
        os.remove(outfile2)

        return youtubeUrls

    else:
        ticket['Publishing.Infile'] = infile
        videoId = uploadVideo(ticket, accessToken, channelId)

        videoUrl = 'https://www.youtube.com/watch?v='+videoId
        logger.info("successfully published Ticket to %s" % videoUrl)
        return [videoUrl,]


def uploadVideo(ticket, accessToken, channelId):
    description = strip_tags(ticket.get('Fahrplan.Description', ''))
    abstract_or_description = strip_tags(ticket.get('Fahrplan.Abstract', description))
    person_list = ticket.get('Fahrplan.Person_list', '')

    description = '%s\n\n%s' % (abstract_or_description, person_list)
    if 'Publishing.Media.Url' in ticket and 'Fahrplan.Slug' in ticket:
        description = os.path.join(ticket['Publishing.Media.Url'], ticket['Fahrplan.Slug']+'.html') + '\n\n' + description

    if 'Publishing.YouTube.TitlePrefix' in ticket:
        tmp_titel = str(ticket['Publishing.YouTube.TitlePrefix']) + ' ' + str(ticket['Fahrplan.Title'])
        logger.debug('adding ' + str(ticket['Publishing.YouTube.TitlePrefix']) + ' as title prefix')
    else:
        tmp_titel = ticket['Fahrplan.Title']
        logger.warn("No youtube title prefix found")

    metadata = {
        'snippet':
        {
            'title': str(tmp_titel),
            'description': description,
            'channelId': channelId,
            'tags': selectTags(ticket)
        },
        'status':
        {
            'privacyStatus': ticket.get('Publishing.YouTube.Privacy', 'private'),
            'embeddable': True,
            'publicStatsViewable': True,
            'license': 'creativeCommon',
        },
    }

    # if tags are set - copy them into the metadata dict
    if 'Publishing.YouTube.Tags' in ticket:
        metadata['snippet']['tags'] = list(map(str.strip, ticket['Publishing.YouTube.Tags'].split(',')))

    # if persons-list is set
    if 'Fahrplan.Person_list' in ticket:
        persons = ticket['Fahrplan.Person_list'].split(',')

        # prepend usernames if only 1 or 2 speaker
        if len(persons) < 3:
            metadata['snippet']['title'] = ticket['Fahrplan.Person_list']+': '+str(ticket['Fahrplan.Title'])

    translation = ticket.get('Publishing.InfileIsTranslated')
    if translation == 'de':
        metadata['snippet']['title'] += ' (deutsche Übersetzung)'

    elif translation == 'en':
        metadata['snippet']['title'] += ' (english translation)'

    # recure limit title length to 100 (youtube api conformity)
    metadata['snippet']['title'] = metadata['snippet']['title'].replace('<', '(').replace('>', ')')
    metadata['snippet']['title'] = metadata['snippet']['title'][:100]



    # 1 => Film & Animation
    # 2 => Autos & Vehicles
    # 10 => Music
    # 15 => Pets & Animals
    # 17 => Sports
    # 18 => Short Movies
    # 19 => Travel & Events
    # 20 => Gaming
    # 21 => Videoblogging
    # 22 => People & Blogs
    # 23 => Comedy
    # 24 => Entertainment
    # 25 => News & Politics
    # 26 => Howto & Style
    # 27 => Education
    # 28 => Science & Technology
    # 30 => Movies
    # 31 => Anime/Animation
    # 32 => Action/Adventure
    # 33 => Classics
    # 34 => Comedy
    # 35 => Documentary
    # 36 => Drama
    # 37 => Family
    # 38 => Foreign
    # 39 => Horror
    # 40 => Sci-Fi/Fantasy
    # 41 => Thriller
    # 42 => Shorts
    # 43 => Shows
    # 44 => Trailers
    if 'Publishing.YouTube.Category' in ticket:
        metadata['snippet']['categoryId'] = int(ticket['Publishing.YouTube.Category'])

    (mimetype, encoding) = mimetypes.guess_type(ticket['Publishing.Infile'])
    size = os.stat(ticket['Publishing.Infile']).st_size

    logger.debug('guessed mimetype for file %s as %s and its size as %u bytes' % (ticket['Publishing.Infile'], mimetype, size))

    r = requests.post(
        'https://www.googleapis.com/upload/youtube/v3/videos',
        params={
            'uploadType': 'resumable',
            'part': 'snippet,status'
        },
        headers={
            'Authorization': 'Bearer '+accessToken,
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Upload-Content-Type': mimetype,
            'X-Upload-Content-Length': size,
        },
        data=json.dumps(metadata)
    )

    if 200 != r.status_code:
        raise RuntimeError('Video creation failed with error-code %u: %s' % (r.status_code, r.text))

    if not 'location' in r.headers:
        raise RuntimeError('Video creation did not return a location-header to upload to: %s' % (r.headers,))

    logger.info('successfully created video and received upload-url from %s' % (r.headers['server'] if 'server' in r.headers else '-'))
    logger.debug('uploading video-data to %s' % r.headers['location'])
    with open(ticket['Publishing.Infile'], 'rb') as fp:
        r = requests.put(
            r.headers['location'],
            headers={
                'Authorization': 'Bearer '+accessToken,
                'Content-Type': mimetype,
            },
            data=fp
        )

        if 200 != r.status_code and 201 != r.status_code:
            raise RuntimeError('uploading video failed with error-code %u: %s' % (r.status_code, r.text))

    video = r.json()

    youtubeurl = 'https://www.youtube.com/watch?v='+video['id']
    logger.info('successfully uploaded video as %s', youtubeurl)

    return video['id']

def getFreshToken(refreshToken, clientId, clientSecret):
    logger.debug('fetching fresh Access-Token on behalf of the refreshToken %s' % refreshToken)
    r = requests.post(
        'https://accounts.google.com/o/oauth2/token',
        data={
            'client_id': clientId,
            'client_secret': clientSecret,
            'refresh_token': refreshToken,
            'grant_type': 'refresh_token',
        }
    )

    if 200 != r.status_code:
        raise RuntimeError('fetching a fresh authToken failed with error-code %u: %s' % (r.status_code, r.text))

    data = r.json()
    if not 'access_token' in data:
        raise RuntimeError('fetching a fresh authToken did not return a access_token: %s' % r.text)

    logger.info("successfully fetched Access-Token %s" % data['access_token'])
    return data['access_token']

def getChannelId(accessToken):
    logger.debug('fetching Channel-Info on behalf of the accessToken %s' % accessToken)
    r = requests.get(
        'https://www.googleapis.com/youtube/v3/channels',
        headers={
            'Authorization': 'Bearer '+accessToken,
        },
        params={
            'part': 'id,brandingSettings',
            'mine': 'true',
        }
    )

    if 200 != r.status_code:
        raise RuntimeError('fetching a fresh authToken failed with error-code %u: %s' % (r.status_code, r.text))

    data = r.json()
    channel = data['items'][0]

    logger.info("successfully fetched Chanel-ID %s with name %s" % (channel['id'], channel['brandingSettings']['channel']['title']))
    return channel['id']


def selectTags(ticket):
    tags = []

    if 'Fahrplan.Track' in ticket:
        tags.append(ticket['Fahrplan.Track'])

    if 'Fahrplan.Day' in ticket:
        tags.append('Day %s' % ticket['Fahrplan.Day'])

    if 'Fahrplan.Room' in ticket:
        tags.append(ticket['Fahrplan.Room'])

    # append language-specific tag
    language = ticket.get('Record.Language')
    if language == 'de':
        tags.append('German')
    elif language == 'en':
        tags.append('English')

    elif language == 'de-en':
        if 'Publishing.InfileIsTranslated' in ticket:
            tags.append('German (english translation)')
        else:
            tags.append('German')

    elif language == 'en-de':
        if 'Publishing.InfileIsTranslated' in ticket:
            tags.append('English (german Übersetzung)')
        else:
            tags.append('English')

    # if persons-list is set
    if 'Fahrplan.Person_list' in ticket:
        persons = ticket['Fahrplan.Person_list'].split(',')

        # append person-names to tags
        tags.extend(persons)

    return tags



class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()
