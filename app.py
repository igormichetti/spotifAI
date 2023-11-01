import os, datetime
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler
from flask import Flask, request, url_for, session, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv, find_dotenv

load_dotenv()

#DIRECT WAY
#os.environ['SPOTIPY_CLIENT_ID'] = 'client id here'
#os.environ['SPOTIPY_CLIENT_SECRET'] = 'client secret here'
os.environ['SPOTIPY_REDIRECT_URI'] = 'http://127.0.0.1:5000/callback'
#os.environ['FLASK_ENV'] = 'development'
#os.environ['FLASK_ENV'] = 'your database uri here' ex: mysql://username:password@localhost/tablename



app = Flask(__name__)
app.secret_key = os.urandom(20).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = datetime.timedelta(minutes=99)

db = SQLAlchemy(app)

argobo = 123

class User(db.Model):
    __tablename__ = 'User'
    user_id = db.Column("id", db.String(12), primary_key=True)
    access_token = db.Column("access_token", db.Text, nullable=False)
    expires_at = db.Column("expires_at", db.Integer, nullable=False)
    expires_in = db.Column("expires_in", db.Integer, nullable=False)
    refresh_token = db.Column("refresh_token", db.Text, nullable=False)
    scope = db.Column("scope", db.Text)
    token_type = db.Column("token_type", db.String(0))

    def __init__(self, user_id, token_info=None):
        self.user_id = user_id
        self.access_token = None
        self.expires_at = None
        self.expires_in = None
        self.refresh_token = None
        self.scope = None
        self.token_type = None

        if token_info: self.update_token_info(token_info)
    
    def update_token_info(self, token_info):
        self.access_token = token_info['access_token']
        self.expires_at = token_info['expires_at']
        self.expires_in = token_info['expires_in']
        self.refresh_token = token_info['refresh_token']
        self.scope = token_info['scope']
        self.token_type = token_info['token_type']
    
    def saved_token_info(self):
        return {'access_token' : self.access_token,
                'expires_at' : self.expires_at,
                'expires_in' : self.expires_in,
                'refresh_token' : self.refresh_token,
                'scope' : self.scope,
                'token_type': self.token_type}

def get_auth_manager():
    scope='user-library-read user-top-read playlist-read-collaborative playlist-read-private playlist-modify-public playlist-modify-private user-read-recently-played user-read-playback-state'
    cache_handler = FlaskSessionCacheHandler(session)
    auth_manager = SpotifyOAuth(scope=scope,
                                cache_handler=cache_handler,
                                show_dialog=True)
    return auth_manager, cache_handler

@app.route('/')
def index():
    auth_manager, cache_handler =  get_auth_manager()

    token_info = cache_handler.get_cached_token()
    if not auth_manager.validate_token(token_info):
        auth_url = auth_manager.get_authorize_url()
        return f'<h2><a href="{auth_url}">Sign in</a></h2>'
    
    sp = Spotify(auth_manager=auth_manager)

    display_name = session.get('display_name', None)
    profile_image = sp.me()['images'][0]["url"]


    return render_template('home.html', display_name=display_name, profile_image=profile_image)

@app.route('/callback')
def callback():
    auth_manager, cache_handler =  get_auth_manager()
    code = request.args.get("code")
    if code:
        token_info = auth_manager.get_access_token(code)
        cache_handler.save_token_to_cache(token_info)
        
        spotify = Spotify(auth_manager=auth_manager)
        user_id = spotify.me()['id']
        session['display_name'] = spotify.me()['display_name']
        session['profile_image'] = spotify.me()['images'][0]['url']
        
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.update_token_info(token_info)
            db.session.commit()
        else:
            new_user = User(user_id, token_info)
            db.session.add(new_user)
            db.session.commit()
        
        return redirect('/')

@app.route('/sign_out/')
def sign_out():
    print(session)
    session.pop("token_info", None)
    session.pop("display_name")
    return redirect('/')

@app.route('/tools/')
def user_top_tracks():
    auth_manager, cache_handler = get_auth_manager()

    token_info = cache_handler.get_cached_token()
    if not auth_manager.validate_token(token_info):
        return redirect('/')

    sp = Spotify(auth_manager=auth_manager)
    tracks = sp.current_user_top_tracks(limit=20, time_range='short_term')
    tracks_info= [(track['name'], track['artists'][0]['name']) for track in tracks['items']]
    
    display_name = session.get('display_name', None)



    return render_template('tools.html', tracks_info=tracks_info, display_name=display_name)

@app.route('/create_user_top_tracks_playlist/')
def create_monthly_playlist():
    auth_manager, cache_handler =  get_auth_manager()

    token_info = cache_handler.get_cached_token()
    if not auth_manager.validate_token(token_info):
        return redirect('/')

    month_year = datetime.datetime.now().strftime('%B %Y')
    playlist_title = f"Top Songs of {month_year}"
    desc = f"This user's most played tracks of {month_year}. Created by Spotifai."

    sp = Spotify(auth_manager=auth_manager)
    tracks = sp.current_user_top_tracks(limit=20, time_range='short_term')
    user_id = sp.me()['id']
    
    playlist = sp.user_playlist_create(user=user_id,
                                        name=playlist_title,
                                        description=desc)
            
    # Add the tracks to the new playlist.
    track_ids = [track['id'] for track in tracks['items']]
    sp.playlist_add_items(playlist["id"], track_ids)
    return redirect('/tools')

@app.route('/playlists/')
def playlists():
    cache_handler = FlaskSessionCacheHandler(session)
    auth_manager = SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.get_access_token(check_cache=True):
        return redirect('/')

    sp = Spotify(auth_manager=auth_manager)
    return sp.current_user_playlists()


@app.route('/currently_playing/')
def currently_playing():
    cache_handler = FlaskSessionCacheHandler(session)
    auth_manager = SpotifyOAuth(cache_handler=cache_handler)
    
    if not auth_manager.get_access_token(check_cache=True):
        return redirect('/')
    
    sp = Spotify(auth_manager=auth_manager)
    track = sp.current_user_playing_track()
    if track:
        return f"<div class='container web-player mb-2 mb-lg-0 ms-auto' id='player' style='max-height: 64px;'><div class='current-album'><img src='{track['item']['album']['images'][-1]['url']}' alt='Album Cover'></div><div class='current-text'><p class='track-name'>{track['item']['name']}</p><a class='track-artist'>{track['item']['artists'][0]['name']}</a></div></div>"
    else:
        return ""

@app.route('/current_user/')
def current_user():
    cache_handler = FlaskSessionCacheHandler(session)
    auth_manager = SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    sp = Spotify(auth_manager=auth_manager)
    return sp.me()

if __name__ == "__main__":
    app.run(debug=True)