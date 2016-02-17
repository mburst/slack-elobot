import time
import json
import re
from slackclient import SlackClient
from tabulate import tabulate
from peewee import *

from models import db, Player, Match

WINNER_REGEX = re.compile('^I crushed <@([A-z0-9]*)> (\d+)-(\d+)', re.IGNORECASE)
CONFIRM_REGEX = re.compile('Confirm (\d+)', re.IGNORECASE)

class EloBot(object):
    def __init__(self, slack_client, channel, config):
        self.last_ping = 0
        self.slack_client = slack_client
        self.channel = channel
        self.config = config
        self.slack_client.rtm_connect()
        self.run()
        
    def heartbeat(self):
        now = int(time.time())
        if now > self.last_ping + 3:
            self.slack_client.server.ping()
            self.last_ping = now
    
    def talk(self, message):
        self.slack_client.api_call('chat.postMessage', channel=self.channel, text=message, username=self.config['bot_name'])
    
    def run(self):
        self.talk(self.config['bot_name'] + ' online!')
        
        while True:
            for message in self.slack_client.rtm_read():
                if message.get('type', False) == 'message' and message.get('channel', False) == self.channel and message.get('text', False):
                    #print message #Useful for debugging
                    if message['text'] == 'Sign me up':
                        self.sign_up(message)
                    elif WINNER_REGEX.match(message['text']):
                        self.winner(message)
                    elif CONFIRM_REGEX.match(message['text']):
                        self.confirm(message)
                    elif message['text'] == 'Print leaderboard':
                        self.print_leaderboard()
            self.heartbeat()
            time.sleep(0.1)
            
    def sign_up(self, message):
        try:
            player = Player.create(slack_id=message['user'])
            self.talk('<@' + message['user'] + '>: ' + 'You\'re all signed up. Good luck!')
        except IntegrityError:
            self.talk('<@' + message['user'] + '>: ' + 'You\'re already signed up!')
    
    def winner(self, message):
        values = re.split(WINNER_REGEX, message['text'])
        
        #0: blank, 1: loser_id, 2: first score, 3: second score, 4: blank
        if not values or len(values) != 5:
            return
        
        try:
            match = Match.create(winner=message['user'], winner_score=values[2], loser=values[1], loser_score=values[3])
            self.talk('<@' + values[1] + '>: Please type "Confirm ' + str(match.id) + '" to confirm the above match or ignore it if it is incorrect')
        except Exception as e:
            self.talk('Unable to save match. ' + str(e))
    
    def confirm(self, message):
        values = re.split(CONFIRM_REGEX, message['text'])
        
        #0: blank, 1: match_id, 2: blank
        if not values or len(values) != 3:
            return
        
        try:
            #http://stackoverflow.com/questions/24977236/saving-peewee-queries-with-multiple-foreign-key-relationships-against-the-same-t
            Winner = Player.alias()
            Loser  = Player.alias()
            match = Match.select(Match, Winner, Loser).join(Winner, on=(Match.winner == Winner.slack_id)).join(Loser, on=(Match.loser == Loser.slack_id)).where(Match.id == values[1], Match.loser == message['user'], Match.pending == True).get()
            
            with db.transaction():
                match.winner.wins  += 1
                match.loser.losses += 1
                
                winner_old_elo = match.winner.rating
                loser_old_elo  = match.loser.rating
                
                #https://metinmediamath.wordpress.com/2013/11/27/how-to-calculate-the-elo-rating-including-example/
                winner_transformed_rating = 10**(match.winner.rating/400.0)
                loser_transformed_rating  = 10**(match.loser.rating/400.0)
                
                winner_expected_score = winner_transformed_rating /(winner_transformed_rating + loser_transformed_rating)
                loser_expected_score  = loser_transformed_rating /(winner_transformed_rating + loser_transformed_rating)
                
                match.winner.rating = round(match.winner.rating + match.winner.k_factor() * (1 - winner_expected_score))
                match.loser.rating = round(match.loser.rating + match.loser.k_factor() * (0 - loser_expected_score))
                
                match.pending = False
                match.save()
                match.winner.save()
                match.loser.save()
            
                self.talk('<@' + match.winner.slack_id + '> your new ELO is: ' + str(match.winner.rating) + ' You won ' + str(match.winner.rating - winner_old_elo) + ' ELO')
                self.talk('<@' + match.loser.slack_id + '> your new ELO is: ' + str(match.loser.rating) + ' You lost ' + str(abs(match.loser.rating - loser_old_elo)) + ' ELO')
        except Exception as e:
            self.talk('Unable to confirm ' + values[1] + '. ' + str(e))
            
    def print_leaderboard(self):
        table = []
        
        for player in Player.select().order_by(Player.rating.desc()).limit(10):
            table.append(['<@' + player.slack_id + '>', player.rating, player.wins, player.losses])
            
        self.talk('```' + tabulate(table, headers=['Name', 'ELO', 'Wins', 'Losses']) + '```')

def get_channel_id(slack_client, channel_name):
    channels = json.loads(slack_client.api_call("channels.list"))
    
    for channel in channels['channels']:
        if channel['name'] == channel_name:
            return channel['id']
    
    print('Unable to find channel: ' + channel_name)
    quit()
    
with open('config.json') as config_data:
    config = json.load(config_data)

slack_client = SlackClient(config['slack_token'])
db.connect()
db.create_tables([Player, Match], True)
EloBot(slack_client, get_channel_id(slack_client, config['channel']), config)
