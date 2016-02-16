# ELO Bot

A basic ELO bot for Slack. Can be used to keep track of the best table tennis or smash player in the office.

## Installation

```
git clone git@github.com:mburst/slack-elobot.git
pip install -r requirements.txt
mv sampleconfig.json config.json
```

Then edit the token value in config.json to match the one acquired from https://api.slack.com/web#authentication

```
python elobot.py
```

Tested on Python 2.7, probably works on 3.x.


## How to use

### Sign up

To signup just type "Sign me up" in the channel specified in the config.json file.

### Declare a winner

If you have beaten someone in a game type "I crushed @username x-y" where x and y are the score as integers. The bot will then ask the loser to confirm the match.

### Confirm a match

To confirm you have lost a match type "Confirm match_id". match_id will be announced by the bot once it is created.

### Print leaderboard

Type "Print leaderboard" in order to see the top 10 players.