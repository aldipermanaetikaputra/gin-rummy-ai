#!/usr/bin/python
#
# genetic_algorithm.py
#
# 2015/04/08
# rg
#
# everything required to create a population, perform cross-overs and mutations and run fitness tests

import random
from texttable import *
from utility import *
from ginmatch import *
from neuralnet import *
from ginstrategy import *
import pickle


class GeneSet(object):
    def __init__(self, genes=None):
        if isinstance(genes, int):
            # create genome of the requested size.
            # for the random seed values, we want to try to pick smart values.
            # let's make 2% of the weights significant and the rest small randoms
            self.genes = []
            [self.genes.append(random.gauss(0, 1)) for _ in range(genes)]

        elif isinstance(genes, list):
            # store genome, ensuring genes are valid
            for gene in genes:
                assert isinstance(gene, float)
                self.genes = genes
        else:
            raise AssertionError("strange value passed in")

    @staticmethod
    def make_geneset(*args, **kwargs):
        return GeneSet(*args, **kwargs)

    # cross the genes of two GeneSets (sexy times)
    def cross(self, partner):
        # return a new GeneSet with length of longest genome
        child = self.make_geneset(max(len(self.genes), len(partner.genes)))

        # cross up to the length of the smallest partner's genome
        big_partner, small_partner = self, partner
        if len(self.genes) < len(partner.genes):
            big_partner, small_partner = partner, self

        # do the cross
        for i in range(len(small_partner.genes)):
            if int(random.random() * 2) == 0:
                child.genes[i] = small_partner.genes[i]
            else:
                child.genes[i] = big_partner.genes[i]

        return child

    # additively mutate our genes (independently) at a given probability
    def mutate(self, probability=None):
        if probability is None:
            probability = 0.001
        for i in range(len(self.genes)):
            if random.random() > 1 - probability:
                self.genes[i] += random.gauss(0, 0.5)


class GinGeneSet(GeneSet):
    def __init__(self, genes=None):
        super(GinGeneSet, self).__init__(genes)

    @staticmethod
    def make_geneset(*args, **kwargs):
        return GinGeneSet(*args, **kwargs)


class Population(object):
    def __init__(self, population_size, retain_best=None, local_storage=None):
        self.member_genes = {}
        self.current_generation = 0
        self.population_size = population_size
        self.num_inputs = 11 + 33
        self.num_outputs = 3
        self.num_hidden = int((self.num_inputs + self.num_outputs) * (2.0 / 3.0))
        self.gene_size = self.num_inputs + (self.num_hidden * self.num_inputs) + (self.num_hidden * self.num_hidden) + (self.num_outputs * self.num_hidden)

        if retain_best is None:
            # by default, keep at least 2 and at most best 10%
            self.retain_best = max(2, int(len(self.member_genes) * 0.10))
        else:
            self.retain_best = retain_best

        # persistent storage location
        if local_storage is None:
            self.local_storage = False
        else:
            self.local_storage = local_storage

        # create the initial genes
        for i in range(population_size):
            self.add_member(GeneSet(self.gene_size), 0, 0)

    # iterate through one generation
    def generate_next_generation(self):
        # test the current generation
        self.fitness_test()

        log_warn(self.draw())

        # cull the meek elders
        self.cull()

        self.cross_over()

        self.current_generation += 1

        # auto-save every so often
        if self.local_storage and self.current_generation % 100 == 0:
            self.persist(action='store')

    # add a member with a given generation
    def add_member(self, geneset, generation, mutation):
        self.member_genes[geneset] = {'game_wins': 0, 'game_draws': 0,
                                      'game_losses': 0, 'game_points': 0, 'generation': generation, 'mutation': mutation}

    # return the top N specimens of the population
    def get_top_members(self, count):

        top_list = sorted(self.member_genes.items(), key=lambda (k, v): self.ranking_func(v), reverse=True)
        top_list = top_list[:count]

        # separate out our keys
        top_keys = []
        [top_keys.append(top_list[i][0]) for i in range(len(top_list))]

        return top_keys

    def ranking_func(self, gene_item):
        game_wins               = gene_item['game_wins']
        game_draws              = gene_item['game_draws']
        game_losses             = gene_item['game_losses']
        game_points             = gene_item['game_points']
        age                     = max(1, float(self.current_generation - gene_item['generation'] + 1))
        points_per_generation   = game_points / age

        try:
            winrate = winrate = ((float(game_wins) * 1.0 + float(game_draws) * 0.5) / float(game_wins + game_losses + game_draws))
        except ZeroDivisionError:
            winrate = 0

        points_per_win = game_points / max(1, game_wins)
        winrate_factor = 100 * winrate

        return (points_per_generation + points_per_win) * winrate_factor
        # return winrate_factor

    # engage each member in competition with each other member, recording the results
    def fitness_test(self):

        # keep track of matches
        matches = []
        player_geneset_dict = {}

        already_tested = []
        for challenger_geneset in self.member_genes:
            for defender_geneset in self.member_genes:
                if challenger_geneset is not defender_geneset:
                    # do not test both A vs B AND B vs A. Just test them once.
                    if (challenger_geneset, defender_geneset) in already_tested or (
                        defender_geneset, challenger_geneset) in already_tested:
                        continue
                    already_tested.append((challenger_geneset, defender_geneset))

                    # create physical representations for these gene_sets
                    challenger_player = GinPlayer()
                    defender_player = GinPlayer()

                    # store these in a lookup table
                    player_geneset_dict[str(challenger_player.id)] = challenger_geneset
                    player_geneset_dict[str(defender_player.id)]   = defender_geneset

                    log_debug("Testing: {0} vs {1}".format(challenger_geneset, defender_geneset))

                    match = GinMatch(challenger_player, defender_player)

                    challenger_weightset = WeightSet(challenger_geneset, self.num_inputs, self.num_hidden, self.num_outputs)
                    defender_weightset = WeightSet(defender_geneset, self.num_inputs, self.num_hidden,self.num_outputs)

                    challenger_observers = [Observer(challenger_player), Observer(match.table)]
                    defender_observers   = [Observer(defender_player), Observer(match.table)]

                    challenger_neuralnet = GinNeuralNet(challenger_observers, challenger_weightset)
                    defender_neuralnet   = GinNeuralNet(defender_observers,   defender_weightset)

                    challenger_strategy = NeuralGinStrategy(challenger_player, defender_player, match,
                                                            challenger_neuralnet)
                    defender_strategy = NeuralGinStrategy(defender_player, challenger_player, match,
                                                          defender_neuralnet)

                    challenger_player.strategy = challenger_strategy
                    defender_player.strategy = defender_strategy

                    # send the match to a worker and store a handle for later use
                    matches.append(match)

        # run matches and record output
        for match in matches:
            # run the match
            match.run()

            p1_gene = player_geneset_dict[str(match.p1.id)]
            p2_gene = player_geneset_dict[str(match.p2.id)]

            # update our records
            self.member_genes[p1_gene]['game_wins']    += match.p1_wins
            self.member_genes[p2_gene]['game_wins']    += match.p2_wins
            self.member_genes[p1_gene]['game_losses']  += match.p1_losses
            self.member_genes[p2_gene]['game_losses']  += match.p2_losses
            self.member_genes[p1_gene]['game_draws']   += match.p1_draws
            self.member_genes[p2_gene]['game_draws']   += match.p2_draws
            self.member_genes[p1_gene]['game_points']  += max(match.p1_score - match.p2_score, 0)
            self.member_genes[p2_gene]['game_points']  += max(match.p2_score - match.p1_score, 0)

    # remove members from prior generations, sparing the top N specimens
    def cull(self):
        # find the top N specimens
        survivor_list = self.get_top_members(self.retain_best)

        # the culling
        for key in self.member_genes.keys():
            if key not in survivor_list:
                del self.member_genes[key]

    # breed the top N individuals against each other, sexually (no asexual reproduction)
    def cross_over(self):
        breeders = self.get_top_members(self.retain_best)

        for breeder in breeders:
            for mate in breeders:
                # prevent asexual reproduction (this will cause result in clone wars)
                if mate is not breeder:
                    newborn = breeder.cross(mate)
                    newborn.mutate(0.075)
                    self.add_member(newborn, self.current_generation + 1, max(self.member_genes[mate]['mutation'],self.member_genes[breeder]['mutation']) + 1)


        # fill the remaining member with random genes
        for i in range(self.population_size - len(self.member_genes)):
            self.add_member(GeneSet(self.gene_size), self.current_generation + 1, 0)

    # TODO: track # of each type of action
    def draw(self):
        # Table 1: print leaderboard
        input_table = Texttable(max_width=115)
        input_table.set_deco(Texttable.HEADER | Texttable.BORDER)
        rows = []
        data_rows = []

        # header row
        rows.append(["ranking",
                     "score",
                     "winrate",
                     "wins",
                     "losses",
                     "draws",
                     "points",
                     "age",
                     "mutation"])

        # gather data on our population
        max_age = 0
        max_score = 0
        max_winrate = 0
        for item in self.member_genes.items():
            value = item[1]

            # track maximum score
            score = self.ranking_func(value)
            if score > max_score:
                max_score = score

            # calculate and track win rate
            try:
                winrate = ((float(value['game_wins']) * 1.0 + float(value['game_draws']) * 0.5) / float(value['game_wins'] + value['game_losses'] + value['game_draws']))
            except ZeroDivisionError:
                winrate = 0.00

            if winrate > max_winrate:
                max_winrate = winrate

            # track maximum age
            age = self.current_generation - value['generation'] + 1
            if age > max_age:
                max_age = age

            # append values
            data_rows.append([score, winrate, value['game_wins'], value['game_losses'], value['game_draws'], value['game_points'], age, value['mutation']])

        # sort by winrate
        data_rows.sort(key=itemgetter(1), reverse=True)

        # collect the top min(10, self.population_size)
#        for i in range(min(10, len(data_rows))):
        for i in range(len(data_rows)):
            # what's our current ranking?
            one_row = [i + 1]
            # the other values defined in the header row
            for j in range(len(rows[0]) - 1):
                one_row.append(data_rows[i][j])
            rows.append(one_row)
        input_table.add_rows(rows[:6])

        output_text = "\n" + "                     LEADERBOARD FOR GENERATION #{0}  (population: {1})".format(
            self.current_generation, len(self.member_genes))

        output_text += "\n" + input_table.draw()

        # log the best score to disk
        try:
            filename = self.local_storage + '.tally'
            with open(filename, 'a+') as the_file:
                best_score = rows[1][2]
                output = str(self.current_generation) + ',' + str(max_score) + ',' + str(max_winrate) + ',' + str(max_age) + "\n"
                the_file.write(output)
        except:
            pass

        return output_text

    def persist(self, action=None):
        assert action is not None, "must specify an action when calling persist()"
        # by default, do not persist
        if not self.local_storage:
            return False

        if action == 'store':
            try:
                pickle.dump(self, open(self.local_storage, 'w'))
                return True
            except:
                return False
        elif action == 'load':
            try:
                # we make a new copy of the object, then we copy its __dict__ into our own __dict__
                restored = pickle.load(open(self.local_storage, 'r'))
                for key in self.__dict__:
                    self.__dict__[key] = restored.__dict__[key]
                return True
            except:
                return False