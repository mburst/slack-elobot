import time
import json
import re
from slackclient import SlackClient
from tabulate import tabulate
from peewee import *
from datetime import datetime
from dateutil import tz

from models import db, Player, Match

SIGNUP_REGEX = re.compile('Sign me up', re.IGNORECASE)
WINNER_REGEX = re.compile('^I\s+(crushed|rekt|beat|whooped)\s+<@([A-z0-9]*)>\s+(\d{1,2})-(\d{1,2})\s*(,\s*(\d{1,2})-(\d{1,2}))*', re.IGNORECASE)
CONFIRM_REGEX = re.compile('Confirm (\d+)', re.IGNORECASE)
CONFIRM_ALL_REGEX = re.compile('Confirm all', re.IGNORECASE)
LEADERBOARD_REGEX = re.compile('Print leaderboard', re.IGNORECASE)
UNCONFIRMED_REGEX = re.compile('Print unconfirmed', re.IGNORECASE)

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('America/Los_Angeles')

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
                    if SIGNUP_REGEX.match(message['text']):
                        self.sign_up(message)
                    elif WINNER_REGEX.match(message['text']):
                        self.winner(message)
                    elif CONFIRM_REGEX.match(message['text']):
                        self.confirm(message['user'], message['text'])
                    elif CONFIRM_ALL_REGEX.match(message['text']):
                        self.confirm_all(message)
                    elif LEADERBOARD_REGEX.match(message['text']):
                        self.print_leaderboard()
                    elif UNCONFIRMED_REGEX.match(message['text']):
                        self.print_unconfirmed()
            self.heartbeat()
            time.sleep(0.1)
            
    def sign_up(self, message):
        if self.is_bot(message['user']):
            self.talk('Nice try, <@' + message['user'] + '>: ' + 'No bots allowed!')
            return

        try:
            player = Player.create(slack_id=message['user'])
            self.talk('<@' + message['user'] + '>: ' + 'You\'re all signed up. Good luck!')
        except IntegrityError:
            self.talk('<@' + message['user'] + '>: ' + 'You\'re already signed up!')
    
    def winner(self, message):
        # 0: space, 1: winning verb, 2: loser_id, 3: first score, 4: second score
        # then 0 or more of...
        # 5: 2nd game hyphenated score, 6: 2nd game first score, 7: 2nd game second score
        msg = message['text']
        values = re.split(WINNER_REGEX, msg)
        if not values or len(values) < 5:
            return

        loser_id = values[2]

        # csv game list starts after the end of the slack username
        games_csv = msg[(msg.index('>') + 1):]
        games = games_csv.replace(' ', '').split(',')

        for game in games:
            scores = game.split('-')
            if len(scores) != 2:
                continue

            first_score = int(scores[0])
            second_score = int(scores[1])

            try:
                match = Match.create(winner=message['user'], winner_score=first_score, loser=loser_id, loser_score=second_score)
                self.talk('<@' + loser_id + '>: Please type "Confirm ' + str(match.id) + '" to confirm the above match or ignore it if it is incorrect')
            except Exception as e:
                self.talk('Unable to save match. ' + str(e))

    def confirm_all(self, message):
        match_list = []
        for match in Match.select(Match).where(Match.loser == message['user'], Match.pending == True):
            match_list.append(match)
        for match in match_list:
            self.confirm(message['user'], 'Confirm '+ str(match.id))
    
    def confirm(self, user, message_text):
        values = re.split(CONFIRM_REGEX, message_text)
        
        #0: blank, 1: match_id, 2: blank
        if not values or len(values) != 3:
            return
        
        try:
            #http://stackoverflow.com/questions/24977236/saving-peewee-queries-with-multiple-foreign-key-relationships-against-the-same-t
            Winner = Player.alias()
            Loser  = Player.alias()
            match = Match.select(Match, Winner, Loser).join(Winner, on=(Match.winner == Winner.slack_id)).join(Loser, on=(Match.loser == Loser.slack_id)).where(Match.id == values[1], Match.loser == user, Match.pending == True).get()
            
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
        min_streak_len = config['min_streak_length']

        for player in Player.select().where((Player.wins + Player.losses) > 0).order_by(Player.rating.desc()).limit(25):
            win_streak = self.get_win_streak(player.slack_id)
            streak_text = ('(won ' + str(win_streak) + ' in a row)') if win_streak >= min_streak_len else ''
            table.append(['<@' + player.slack_id + '>', player.rating, player.wins, player.losses, streak_text])

        self.talk('```' + tabulate(table, headers=['Name', 'ELO', 'Wins', 'Losses', 'Streak']) + '```')

    def print_unconfirmed(self):
        table = []

        Winner = Player.alias()
        Loser  = Player.alias()
        for match in Match.select(Match, Winner, Loser).join(Winner, on=(Match.winner == Winner.slack_id)).join(Loser, on=(Match.loser == Loser.slack_id)).where(Match.pending == True).order_by(Match.played.desc()).limit(25):
            match_played_utc = match.played.replace(tzinfo=from_zone)
            match_played_pst = match_played_utc.astimezone(to_zone)
            table.append([match.id, '<@' + match.loser.slack_id + '>', '<@' + match.winner.slack_id + '>', str(match.winner_score) + '-' + str(match.loser_score), match_played_pst.strftime('%m/%d/%y %I:%M %p')])

        self.talk('```' + tabulate(table, headers=['Match', 'Needs to Confirm', 'Opponent', 'Score', 'Date']) + '```')

    def is_bot(self, user_id):
        return self.slack_client.api_call('users.info', user=user_id)['user']['is_bot']

    def get_win_streak(self, player_slack_id):
        win_streak = 0
        matches = Match.select().where(Match.pending == False, (player_slack_id == Match.winner) | (player_slack_id == Match.loser)).order_by(Match.played.desc())
        for match in matches:
            if (player_slack_id == match.winner_id):
                win_streak = win_streak + 1
            else:
                break

        return win_streak

def get_channel_id(slack_client, channel_name):
    channels = slack_client.api_call("channels.list")

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
