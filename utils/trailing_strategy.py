class Tralling:
    def __init__(self, configs, exit_strategy):
        self.initial_config = configs
        self.PROFIT_TRAIL = configs['profit_trail_start_at']
        self.LOCK_PROFIT = configs['profit_lock_after_start']
        self.PROFIT_TRAIL_UPDATE = configs['on_profit_increase_from_trail']
        self.INCREASE_PROFIT_LOCK = configs['increase_profit_lock_by']
        self.TRALING_STARTED = False
        self.exit = exit_strategy

    def trailing(self, pnl):
        try:
            if pnl >= self.PROFIT_TRAIL:
                self.TRALING_STARTED = True

            if self.TRALING_STARTED:
                if pnl >= (self.PROFIT_TRAIL + self.PROFIT_TRAIL_UPDATE):
                    self.update_profit_trail()
                if pnl <= self.LOCK_PROFIT:
                    self.exit()
        except Exception as e:
            raise ValueError(f'error in trailing')
        
    def update_profit_trail(self):
        self.PROFIT_TRAIL = self.PROFIT_TRAIL + self.PROFIT_TRAIL_UPDATE
        self.LOCK_PROFIT = self.LOCK_PROFIT + self.INCREASE_PROFIT_LOCK