# match_engine/scoreboard.py

class Scoreboard:
    def __init__(self):
        # List of tuples (away_runs, home_runs) for each inning
        # e.g. [(0, 0), (1, 0), (0, 2)]
        self.innings = [] 

    def record_inning(self, inning_num, away_runs, home_runs):
        """
        Updates the scoreboard for a specific inning.
        """
        # Extend list if needed to reach the inning number
        while len(self.innings) < inning_num:
            self.innings.append([0, 0])
        
        # Inning num is 1-based, list is 0-based
        self.innings[inning_num-1] = [away_runs, home_runs]

    def print_board(self, state):
        """
        Prints the ASCII scoreboard to the console.
        """
        print("\nSCOREBOARD")
        # Header: INN | 1 2 3 ... | R | H | E
        header_inn = "  ".join(f"{i+1}" for i in range(len(self.innings)))
        print(f"INN | {header_inn} | R  | H  | E")
        print("----|-" + "--" * len(self.innings) + "-|----|----|---")
        
        # Calculate totals
        total_away = sum(inn[0] for inn in self.innings if inn[0] is not None)
        total_home = sum(inn[1] for inn in self.innings if inn[1] is not None)
        
        # Away Row
        # If runs is None (e.g. bottom of 9th not played), show 'x' or ' '
        away_scores = "  ".join(f"{inn[0]}" if inn[0] is not None else " " for inn in self.innings)
        print(f"{state.away_team.name[:3]} | {away_scores} | {total_away:<2} | -- | --")
        
        # Home Row
        home_scores = "  ".join(f"{inn[1]}" if inn[1] is not None else " " for inn in self.innings)
        print(f"{state.home_team.name[:3]} | {home_scores} | {total_home:<2} | -- | --")
        print("")