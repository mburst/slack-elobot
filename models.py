from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase
#import logging
#logger = logging.getLogger('peewee')
#logger.setLevel(logging.DEBUG)
#logger.addHandler(logging.StreamHandler())

db = SqliteExtDatabase('elo.db')

class BaseModel(Model):
    class Meta:
        database = db

class Player(BaseModel):
    slack_id = CharField(primary_key=True)
    rating   = FloatField(default=1500)
    wins     = IntegerField(default=0)
    losses   = IntegerField(default=0)
    
    def k_factor(self):
        if self.rating > 2400:
            return 16
        elif self.rating < 2100:
            return 32
        
        return 24
        
class Match(BaseModel):
    winner       = ForeignKeyField(Player, related_name='matches_won')
    winner_score = IntegerField(default=0)
    loser        = ForeignKeyField(Player, related_name='matches_lost')
    loser_score  = IntegerField(default=0)
    pending      = BooleanField(default=True)
    played       = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
    
    class Meta:
        indexes = (
            # Specify a unique multi-column index on from/to-user.
            (('winner', 'loser'), True),
        )