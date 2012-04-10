import cgi
from us_account import US_Account

ICON_MOVIES     = 'icon-movie.png'

MOVIE_PATTERN   = Regex('^http://api.netflix.com/catalog/titles/movies/[0-9]+$')
TVSHOW_PATTERN  = Regex('^http://api.netflix.com/catalog/titles/series/[0-9]+$')
SEASON_PATTERN  = Regex('^http://api.netflix.com/catalog/titles/series/[0-9]+/seasons/[0-9]+$')
EPISODE_PATTERN = Regex('^http://api.netflix.com/catalog/titles/programs/[0-9]+/[0-9]+')

EPISODE_TITLE_PATTERN = Regex('^S(?P<season>[0-9]+):E(?P<episode>[0-9]+) - (?P<title>.+)$')

###################################################################################################

def MainMenu():

  # Attempt to log in
  logged_in = US_Account.LoggedIn()
  if not logged_in:
    logged_in = US_Account.TryLogIn()

  oc = ObjectContainer()

  if logged_in:

    # If the user is currently logged in, then we have validated their credentials and will be able 
    # to access their associated (personalized) content list.
    user_id = US_Account.GetUserId()
    user_list_url = US_Account.GetAPIURL('http://api.netflix.com/users/%s/lists' % user_id, params = { 'v': '2', 'client': 'plex' })
    user_list = XML.ElementFromURL(user_list_url)

    # Add the found items
    for item in user_list.xpath('//lists/list/link'):
      url = item.get('href')
      title = item.get('title')
      oc.add(DirectoryObject(key = Callback(MenuItem, url = url, title = title), title = title))

  else:

    # The user has not yet provided valid credentials. Therefore, we should allow them to be redirected
    # to sign up for a free trial.
    oc.add(DirectoryObject(key = Callback(FreeTrial), title = 'Sign up for free trial', thumb = R(ICON_MOVIES)))

  oc.add(PrefsObject(title = 'Preferences'))

  return oc

###################################################################################################

@route('/video/netflix/us/freetrial')
def FreeTrial():
  url = "http://www.netflix.com/"
  webbrowser.open(url, new=1, autoraise=True)
  return MessageContainer("Free Trial Signup", """A browser has been opened so that you may sign up for a free trial.  If you do not have a mouse 
      and keyboard handy, visit http://www.netflix.com and sign up for free today!""")

###################################################################################################

@route('/video/netflix/us/menuitem')
def MenuItem(url, title):
  oc = ObjectContainer(title2 = title)

  # Separate out the specified parameters from the original URL
  params = {}
  if url.find('?') > -1:
    original_params = String.ParseQueryString(url[url.find('?') + 1:])
    for key, value in original_params.items():
  	 params[key] = value[0]

  # Add the additional parameters to ensure that we get all of the required items expaned.
  params['expand'] = '@title,@box_art,@synopsis,@directors,@seasons,@episodes'
  menu_item_url = US_Account.GetAPIURL(url, params = params)
  menu_item = XML.ElementFromURL(menu_item_url)

  for item in menu_item.xpath('//catalog_title'):

    item_details = ParseCatalogueItem(item)

    # Movies
    if MOVIE_PATTERN.match(item_details['id']):
      oc.add(MovieObject(
        items = [ MediaObject(parts = [PartObject(key = Callback(PlayVideo, url = item_details['url']))], protocol = 'webkit') ],
        key = item_details['id'],
        rating_key = item_details['id'],
        title = item_details['title'],
        thumb = item_details['thumb'][0],
        summary = item_details['summary'],
        genres = item_details['genres'],
        directors = item_details['directors'],
        duration = item_details['duration'],
        rating = item_details['rating'],
        content_rating = item_details['content_rating']))

    # TV Shows
    elif TVSHOW_PATTERN.match(item_details['id']):
      oc.add(TVShowObject(
        key = Callback(MenuItem, url = item_details['season_url'], title = item_details['title']),
        rating_key = item_details['id'],
        title = item_details['title'],
        thumb = item_details['thumb'][0],
        summary = item_details['summary'],
        genres = item_details['genres'],
        duration = item_details['duration'],
        rating = item_details['rating'],
        content_rating = item_details['content_rating']))

    # TV Show Seasons
    elif SEASON_PATTERN.match(item_details['id']):
      oc.add(SeasonObject(
        key = Callback(MenuItem, url = item_details['episode_url'], title = item_details['title']),
        rating_key = item_details['id'],
        title = item_details['title'],
        thumb = item_details['thumb'][0],
        summary = item_details['summary'],
        episode_count = item_details['episode_count']))

    # TV Episodes
    elif EPISODE_PATTERN.match(item_details['id']):
      oc.add(EpisodeObject(
        items = [ MediaObject(parts = [PartObject(key = Callback(PlayVideo, url = item_details['url']))], protocol = 'webkit') ],
        key = item_details['id'],
        rating_key = item_details['id'],
        title = item_details['title'],
        show = item_details['show'],
        season = item_details['season_index'],
        index = item_details['episode_index'],
        thumb = item_details['thumb'][0],
        summary = item_details['summary'],
        directors = item_details['directors'],
        duration = item_details['duration'],
        rating = item_details['rating'],
        content_rating = item_details['content_rating']))

  return oc

###################################################################################################

def ParseCatalogueItem(item):

  id = item.xpath('.//id/text()')[0]

  title_node = item.xpath('.//title')[0]
  title = title_node.get('short')

  video_url = item.xpath('.//link[contains(@title, "web page")]')[0].get('href')
  summary = item.xpath('.//synopsis//text()')[0]
  content_rating = item.xpath('.//category[contains(@scheme, "_ratings")]')[0].get('term')

  directors = item.xpath('.//link[contains(@title, "directors")]/people/link')
  directors = [ director.get('title') for director in directors ]

  genres = item.xpath('.//category[contains(@scheme, "http://api.netflix.com/categories/genres")]')
  genres = [ genre.get('label') for genre in genres]

  # [Optional]
  rating = None
  try: rating = float(item.xpath('.//average_rating/text()')[0]) * 2
  except: pass

  # [Optional]
  # Only certain items have durations (e.g. a TV Show Season does not)
  duration = None
  try: duration = int(item.xpath('.//runtime/text()')[0]) * 1000
  except: pass

  # There are mutiple resolutions available for artwork. We will just try to find all available and build up a list
  # with the highest first.
  artwork = []
  artwork_resolutions = ['HD box art', 'large box art', 'medium box art', 'small box art']
  for resolution in artwork_resolutions:
    node = item.xpath('.//box_art/link[contains(@title, "%s")]' % resolution)
    if len(node) == 1:
      artwork.append(node[0].get('href'))

  # [Optional]
  # Attempt to extract any episode details from the title
  # Example: The Office: Season 1: Pilot
  show = None
  episode_title_regular = title_node.get('regular')
  if episode_title_regular:
    show = episode_title_regular.split(':')[0]

  # [Optional]
  # Example: S1:E1 - Pilot
  season_index = None
  episode_index = None
  episode_title_short = title_node.get('episode_short')
  if episode_title_short:
    episode_details = EPISODE_TITLE_PATTERN.match(episode_title_short)
    if episode_details:
      episode_details_dict = episode_details.groupdict()
      title = episode_details_dict['title']
      season_index = int(episode_details_dict['season'])
      episode_index = int(episode_details_dict['episode'])

  # [Optional]
  episode_count = None
  try: episode_count = int(item.xpath('.//link[contains(@title, "episodes")]/catalog_titles/number_of_results/text()')[0])
  except: pass

  # [Optional]
  # If the item represents a TV Show, then it will contain a URL to access the available seasons
  season_url = None
  try: season_url = item.xpath('.//link[contains(@title, "seasons")]')[0].get('href')
  except: pass

  # [Optional]
  # If the item represents a TV Show Season, then it will contain a URL to access the available episodes
  episode_url = None
  try: episode_url = item.xpath('.//link[contains(@title, "episodes")]')[0].get('href')
  except: pass

  return {
    'id': id,
    'url': video_url,
    'season_url': season_url,
    'episode_url': episode_url,
    'title': title,
    'show': show,
    'season_index': season_index,
    'episode_index': episode_index,
    'episode_count': episode_count,
    'summary': summary,
    'duration': duration,
    'rating': rating,
    'content_rating': content_rating,
    'directors': directors,
    'genres': genres,
    'thumb': artwork}

###################################################################################################

def SetRating(key, rating):
  pass

###################################################################################################

@route('/video/netflix/us/playvideo')
def PlayVideo(url):

  movie_id = re.match('http://www.netflix.com/Movie/.+/(?P<id>[0-9]+)', url).groupdict()['id']
  player_url = 'http://www.netflix.com/WiPlayer?movieid=%s' % movie_id
  user_url = "http://api.netflix.com/users/%s" % US_Account.GetUserId()

  params = {'movieid': movie_id, 'user': user_url}
  video_url = US_Account.GetAPIURL(player_url, params = params)
  return Redirect(WebVideoURL(video_url))