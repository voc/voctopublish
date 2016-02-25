class Ticket:
    def __init__(self, ticket, ticket_id):
        self.__tracker_ticket = ticket
        self.ticket_id = ticket_id
        self.slug = self._validate_('Fahrplan.Slug')
        self.guid = self._validate_('Fahrplan.GUID')
        self.fahrplan_id = self._validate_('Fahrplan.ID')
        self.title = self._validate_('Fahrplan.Title')
        self.subtitle = self._validate_('Fahrplan.Subtitle')
        self.acronym = self._validate_('Project.Slug')
        self.abstract = self._validate_('Fahrplan.Abstract')
        self.profile_extension = self._validate_('EncodingProfile.Extension')
        self.profile_slug = self._validate_('EncodingProfile.Slug')
        self.filename = self._validate_('EncodingProfile.Basename') + "." + self.profile_extension
        self.folder = self._validate_('EncodingProfile.MirrorFolder')
        self.local_filename = self.fahrplan_id + "-" + self.slug + "." + self.profile_extension
        self.local_filename_base = self.fahrplan_id + "-" + self.profile_slug
        self.video_base = self._validate_('Publishing.Path')
        self.output = self.video_base # TODO remove
        self.download_base_url = self._validate_('Publishing.Base.Url')
        self.language = self._validate_('Record.Language')
        self.language_index = int(self._validate_('Encoding.LanguageIndex'))
        self.language_template = self._validate_('Encoding.LanguageTemplate')
        self.profile_youtube_enable = self._validate_('Publishing.YouTube.EnableProfile')
        self.youtube_enable = self._validate_('Publishing.YouTube.Enable')
        self.profile_media_enable = self._validate('Publishing.Media.EnableProfile')
        self.media_enable = self._validate_('Publishing.Media.Enable')
        self.people = []
        if 'Fahrplan.Person_list' in ticket:
            self.people = self._validate_('Fahrplan.Person_list').split(', ')
            
        self.tags = [self.acronym]
        if 'Media.Tags' in ticket:
            self.tags = self._validate_('Media.Tags').replace(' ', '').split(',')
        
        # check if this event has already been published to youtube
        self.has_youtube_url = False
        if 'YouTube.Url0' in ticket and self._validate_('YouTube.Url0') is not None:
            self.has_youtube_url = True

    def _validate_(self, key):
        value = None
        if key in self.__tracker_ticket:
            value = str(self.__tracker_ticket[key])
        
        return value
    
    