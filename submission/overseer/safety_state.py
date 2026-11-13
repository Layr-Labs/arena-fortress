"""Safety-state initializers adapted from e-man07 65e60732, ab1668c0575c85ae1971d528b88bdaeb14b94b53."""

def initialize(self):
    self.beds_first = False
    self.lab = False
    self.culled = {}
    self.brew_stopped = False
    self.sheltered = {}
    self.stairs = {}
    self.surface_seen = None
    self.lock = None
    self.wild_off = False
    self.own_locks = set()
    self.rest_until = 0
    self.alert_pending = False
    self.calm = None
    self.calm_fail = 0
    self.calm_ok = False
    self.beast_seen = False
    self.beast_view = None
    self.thaw_alert = False
    self.beast_told = []
    self.beast_fail = 0
    self.beast_spent = 0
    self.fell = None
