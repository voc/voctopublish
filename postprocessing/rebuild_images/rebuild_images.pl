#!/usr/bin/env perl

#
# Rebuilds video thumbnails and previews using 
# regenerate_thumb.sh script.
#
# Uses data from the public api of media.ccc
#
# Continues where it left of in case of an error, writes log to $processed_events_file
#

#
# PREREQUISITES:
#
# apt-get install libjson-perl libjson-xs-perl libwww-perl liblog-log4perl-perl liburi-perl
#

use utf8;
binmode(STDOUT, ":utf8");
binmode(STDERR, ":utf8");
use strict;
use warnings;

use Getopt::Long;
use JSON qw(decode_json);
use List::Util qw(min max);
use Log::Log4perl qw(:easy);
use URI::URL;
use LWP::UserAgent;


#
# Configuration
#

# Where to find the thumbnail generation script
my $rebuild_cmd = '../generate_thumb_autoselect_compatible.sh';

# Set this to a local directory, recordings are searched here and used for
# thumbnail generation.
#
# If you are not using a local repo and you are just testing, you might want to
# reduce the image samples in the generation shell script to one, otherwise it takes
# forever. 
#
# If is the part of the recording url that will take the place of $media_ccc_events_url
# For example:
#    media_ccc_events_url = 'http://cdn.media.ccc.de/events'
#    local_mirror = '/var/www/media.ccc.de/events'
#
#    [http://cdn.media.ccc.de/events]/froscon/2014/mp4/froscon2014-1372-DE-Our_Puppet_Story_h264-hq.mp4
#    =>
#    [/var/www/media.ccc.de/events]/froscon/2014/mp4/froscon2014-1372-DE-Our_Puppet_Story_h264-hq.mp4
#
# my $local_mirror = '/var/www/media.ccc.de';
my $local_mirror = undef;

# URL found as recordings base on media.ccc.de, used for replacement with $local_mirror
my $media_ccc_events_url = 'http://cdn.media.ccc.de';

# media.ccc.de API starting point
my $api_base_url = 'https://api.media.ccc.de/public/';

# Where the thumbnail files of media.ccc.de are located (used for search /
# replace)
my $static_file_base_url = 'https://static.media.ccc.de/media/';


#
# CLI Args
#

my $verbose;
my $noop;

sub print_help {
  print <<HERE
  -n | --noop         Do not create any files
  -v | --verbose      Add verbose output
  -h | --help         Print this help
HERE
}

GetOptions(
  "verbose"  => \$verbose,
  "noop" => \$noop,
  "help" => sub { print_help(); exit(0); }
) or die 'Error parsing command line arguments.';

#
# Globals
#

Log::Log4perl->easy_init(($verbose) ? $DEBUG : $INFO);

my $ua = LWP::UserAgent->new;
$ua->agent('rebuild-thumb-images');

my $processed_events_file = 'rebuild_images_events_done.delme.txt';
my $PROCESSED_EVENTS_FH;
my %previously_processed_events;

#
# Functions
#

sub open_and_load_processed_events {
  return if $noop;

  DEBUG 'reading previously processed events file';

  open $PROCESSED_EVENTS_FH, "+>>$processed_events_file" or die "Could not open $processed_events_file $!";
  seek $PROCESSED_EVENTS_FH, 0, 0;

  foreach my $guid_line (<$PROCESSED_EVENTS_FH>)  {   
    chomp($guid_line);
    $previously_processed_events{$guid_line} = 1;
  }

  DEBUG sprintf('read %d previously processed events', scalar(keys %previously_processed_events));
}

sub is_event_already_processed {
  my ($event) = @_;
  return 0 if $noop;

  return defined $previously_processed_events{$event->{url}};
}

sub mark_event_as_processed {
  my ($event) = @_;
  return if $noop;

  $previously_processed_events{$event->{url}} = 1;
  print $PROCESSED_EVENTS_FH "$event->{url}\n";
}

sub close_processed_events {
  return if $noop;

  DEBUG 'closing previously processed events file';
  close $PROCESSED_EVENTS_FH;
}

sub _get_url {
  my ($url) = @_;
  my $response = $ua->get($url);
  if ($response->is_success) {
    return decode_json($response->decoded_content);
  }
  else {
    die "Could not GET '$url': ". $response->status_line;
  }
}

sub get_conference_list {
  return _get_url($api_base_url .'/conferences')->{'conferences'};
}

sub get_conference_details {
  my ($conference) = @_;
  return _get_url($conference->{url});
}

sub get_event_details {
  my ($event) = @_;
  return _get_url($event->{url});
}

# Determins the rank or score of an recording based on it's meta information.
# Returns: an integer, higher means better.
# The high quality flag, mime type and resolution is taken into account in the
# given order.
sub recording_score {
  my ($recording) = @_;
  my $score = 0;
  $score += 1_000_000 if $recording->{high_quality};
  $score +=   100_000 * mime_rank($recording);
  $score +=    $recording->{width} + $recording->{height}; # works till videos are > 5k
  return $score;
}

my %VIDEO_RANK = (
  'video/mp4'  => 3,
  'video/webm' => 2,
  'video/ogg'  => 1
);

# Returns: an integer [0,9] representing the ranking of the recording by it's mime
# type. Higher means better. mp4 is 3 for example, unkown is 0.
sub mime_rank {
  my ($recording) = @_;
  return $VIDEO_RANK{$recording->{mime_type}} if (defined $VIDEO_RANK{$recording->{mime_type}});
  return 0;
}

sub _filter_video_recordings {
  my ($recordings) = @_;
  return grep {
    $_->{mime_type} =~ m/^video/
  } @$recordings;
}

sub _sort_video_recordings_by_score_desc {
  my ($recordings) = @_;
  return sort {
    return recording_score($b) - recording_score($a)
  } @$recordings;
}

# Tries to determine the main recording of an event by looking at the meta
# information of the recordings, searches for the video with the best quality.
# Returns: selected api recordings object
sub determine_main_recording {
  my ($event) = @_;

  my @recordings = @{$event->{recordings}};
  @recordings = _filter_video_recordings(\@recordings);
  return unless @recordings > 0;
  @recordings = _sort_video_recordings_by_score_desc(\@recordings);

  DEBUG "  recordings \n  - ", join("\n  - ", map { $_->{filename} .' (score '. recording_score($_) .')' } @recordings);
  return shift @recordings;
}

# determine recording video file location, switched between local or remote
# depending on the $local_mirror value
# Returns: local file path or URL
sub get_recording_location {
  my ($recording) = @_;

  my $recording_url = $recording->{recording_url};

  if ($local_mirror) {
    $recording_url =~ s#^$media_ccc_events_url#$local_mirror#;
    die "Recording '$recording_url' not found locally" unless -e $recording_url;
  }

  return $recording_url
}

sub _remove_media_prefix_from_url {
  my ($url) = @_;
  $url =~ s/^$static_file_base_url//;
  return $url;
}

sub determine_images_output_dir {
  my ($conference) = @_;
  return _remove_media_prefix_from_url($conference->{images_url});
}

sub run_generate_thumb_command {
  my %params = @_;
  my $cmd = "$rebuild_cmd \"$params{recording}\" \"$params{output_dir}\" \"$params{thumb_filename}\" \"$params{preview_filename}\" 2>&1";
  DEBUG "executing: $cmd";

  return if $noop;

  my $output = `$cmd`;
  if ($? != 0) {
    die "rebuild command failed: $output";
  }

  DEBUG "output is: $output" if $output;
}

sub get_relative_image_url {
  my ($conference, $url) = @_;
  my $filename = $url;
  $filename =~ s#^$conference->{images_url}/?##;
  return $filename;
}

sub rebuild_images_for_event {
  my ($conference, $event, $output_dir) = @_;

  DEBUG "rebuilding images for event '$event->{title}' ($event->{url})";

  my $main_recording = determine_main_recording($event);
  return unless $main_recording;

  my $recording_location = get_recording_location($main_recording);
  DEBUG "recording location: ", $recording_location;

  run_generate_thumb_command(recording        => $recording_location,
                             output_dir       => $output_dir,
                             thumb_filename   => get_relative_image_url($conference, $event->{thumb_url}),
                             preview_filename => get_relative_image_url($conference, $event->{poster_url})
  );

  mark_event_as_processed($event);
}

sub rebuild_images_for_conference {
  my ($conference) = @_;

  my $images_output_dir = determine_images_output_dir($conference);
  DEBUG "conference image output dir: ", $images_output_dir;

  my $events = $conference->{'events'};
  for my $event_idx (0 .. (@$events - 1)) {
    my $event = $events->[$event_idx];
    eval {
      if (is_event_already_processed($event)) {
        DEBUG "event '$event->{title}' ($event->{url}) already processed, skipping";
        return;
      }
      
      my $event_details = get_event_details($event);
      rebuild_images_for_event($conference, $event_details, $images_output_dir);

      INFO sprintf('     (%3d of %3d) event: %s (%s) done',
                    $event_idx + 1,
                    scalar(@$events),
                    $event->{title},
                    $event->{url});
    };
    if ($@) {
      my $error = $@;
      chomp($error);
      ERROR sprintf("failed to rebuild images for '%s' (%s) event '%s' (%s) message '%s'",
                      $conference->{title}, $conference->{url},
                      $event->{title}, $event->{url},
                      $error);
    }
  }
}

#
# main
#

sub main {
  open_and_load_processed_events();
  my $conferences = get_conference_list();
  
  INFO sprintf("rebuilding thumbnail and preview images for %d conferences", scalar(@$conferences));
  
  for my $conference_idx (0 .. (@$conferences - 1)) {
    my $conference_details = get_conference_details($conferences->[$conference_idx]);

    INFO sprintf("%3d of %3d: conference '%s' (%s)",
      $conference_idx + 1,
      scalar(@$conferences),
      $conference_details->{title},
      $conference_details->{url});

    rebuild_images_for_conference($conference_details);
  }
  
  close_processed_events();
  INFO "done";
}

main();
