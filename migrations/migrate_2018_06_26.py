from models_2018_06_26 import Player as Player_2018_06_26
from models_2018_06_26 import Match as Match_2018_06_26
from models import db, Match

def migrate():
    old_matches = list(Match_2018_06_26.select().order_by(Match_2018_06_26.id))
    print('old matches: {}'.format(old_matches))
    def convert_match(old_match):
        return Match(
            winner_handle=old_match.winner.slack_id,
            winner_score=old_match.winner_score,
            loser_handle=old_match.loser.slack_id,
            loser_score=old_match.loser_score,
            pending=old_match.pending,
            played=old_match.played)
    new_matches = [ convert_match(old_match) for old_match in old_matches ]
    print('new matches (not yet committed): {}'.format(new_matches))

    print('dropping old Match table')
    db.drop_tables([Match_2018_06_26])
    print('dropping old Player table')
    db.drop_tables([Player_2018_06_26])

    print('creating new Match table')
    Match.create_table()
    print('saving new matches')
    for new_match in new_matches:
        new_match.save()

if __name__ == '__main__':
    print('running 2018_06_26 migration')
    print('the current database schema is expected to be')
    print("""
class Player(BaseModel):
    slack_id = CharField(primary_key=True)
    rating   = IntegerField(default=1500)
    wins     = IntegerField(default=0)
    losses   = IntegerField(default=0)
class Match(BaseModel):
    winner       = ForeignKeyField(Player, related_name='matches_won')
    winner_score = IntegerField(default=0)
    loser        = ForeignKeyField(Player, related_name='matches_lost')
    loser_score  = IntegerField(default=0)
    pending      = BooleanField(default=True)
    played       = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
    """)
    print('connecting to db')
    db.connect()
    print('beginning migration')
    migrate()
    print('all done!')
