#!/usr/bin/python
#
# ginplayer.py
#
# 2014/01/18
# rg
#
# base classes for gin rummy player

from ginhand import *
from ginstrategy import *
from gintable import *
from observer import *


# handle invalid draws. retain who did it so we can weed them out of existence.
class DrawException(Exception):
    def __init__(self, who):
        super(DrawException, self).__init__(self)
        self.who = who


# handle invalid strategies
class StrategyExecutionException(Exception):
    pass


# the player
class GinPlayer(Observable):
    # begin with empty hand
    def __init__(self, strategy=False):
        super(GinPlayer, self).__init__()
        # parameter passing
        self.strategy = strategy

        self.action = False

        self.table = False

        self.hand = GinHand()

        self._knock_listeners = []
        self._knock_gin_listeners = []

        # at most, we have 11 interesting things to offer our observer
        self.observable_width = 11

    # listen for knocks
    def register_knock_listener(self, listener):
        if not listener in self._knock_listeners:
            self._knock_listeners.append(listener)

    def notify_knock_listeners(self):
        for listener in self._knock_listeners:
            listener.notify_of_knock(self)

    # discard one card and knock
    def knock(self, card):
        self.discard_card(card)
        self.notify_knock_listeners()

    # listen for gins
    def register_knock_gin_listener(self, listener):
        if not listener in self._knock_gin_listeners:
            self._knock_gin_listeners.append(listener)

    def notify_knock_gin_listeners(self):
        for listener in self._knock_gin_listeners:
            listener.notify_of_knock_gin(self)

    # discard one card and knock
    def knock_gin(self, card):
        self.discard_card(card)
        self.notify_knock_gin_listeners()

    # sit at a table
    def sit_at_table(self, table):
        if table.seat_player(self):
            self.table = table

    # add the given card to this player's hand
    @notify_observers_after  # here mostly to satisfy unit tests
    def _add_card(self, card):
        self.hand.add_card(card)

    # implement the Observable criteria. return a dict of ints representing our hand. key corresponds to hand.cards idx
    # note that we have 11 "slots". One may be empty at times. We use 0 as the empty encoding.
    def organize_data(self):
        indexes = range(len(self.hand.cards))
        rankings = [c.ranking() for c in self.hand.cards]

        # make sure we return 11 values. 0 means no card.
        if len(self.hand.cards) == 10:
            indexes.append(10)
            rankings.append(0)

        return dict(zip(indexes, rankings))

    def draw(self):
        if self.hand.size() == 11:
            raise DrawException(self)
        else:
            card = self.table.deal_a_card()
            self._add_card(card)
            return card

    def consult_strategy(self, phase):
        self.action = self.strategy.determine_best_action(phase)

    # here we act on the advice we received from the strategy
    @notify_observers_after
    def execute_strategy(self):
        card = None
        if not self.action:
            raise StrategyExecutionException('no action to execute!')
        else:
            if self.action[0] == 'DRAW':
                self.draw()
            elif self.action[0] == 'PICKUP-FROM-DISCARD':
                self.pickup_discard()
            elif self.action[0] == 'DISCARD':
                index = self.action[1]
                card = self.hand.get_card_at_index(index)
                self.discard_card(card)
            elif self.action[0] == 'KNOCK':
                index = self.action[1]
                card = self.hand.get_card_at_index(index)
                self.knock(card)
            elif self.action[0] == 'KNOCK-GIN':
                index = self.action[1]
                card = self.hand.get_card_at_index(index)
                self.knock_gin(card)

        log_debug("\t\tAction taken: {0}  \t{1}".format(self.action[0], card))

    # consult the strategy and perform the action suggested
    def take_turn(self):
        # ensure we have enough cards to take a turn
        assert self.hand.size() >= 10, "Not enough cards in hand"

        # if we have 10 cards, we do this twice. otherwise (we have 11 cards), we do it once.
        if self.hand.size() == 10:
            self.consult_strategy(phase='start')
            self.execute_strategy()

        self.consult_strategy(phase='end')
        self.execute_strategy()

    def pickup_discard(self):
        card = self.table.pickup_from_discard_pile()
        self._add_card(card)
        return card

    # drop the given card into the discard pile
    def discard_card(self, card):
        try:
            self.hand.discard(card)
            self.table.add_card_to_discard_pile(card)
        except ValueError:
            raise Exception("card not in our hand")
        except AttributeError:
            raise Exception("cards not behaving like a list: " + AttributeError.message)
        return card

    # empty the player's hand
    def empty_hand(self):
        self.hand = GinHand()