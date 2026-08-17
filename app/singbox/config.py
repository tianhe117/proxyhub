"""db -> config.json generator (pure function, easy to unit-test).

Does not depend on process.py / client.py; only maps
database state -> sing-box config.
Tag convention: inbound i{id}, selector g{id}, real node n{id}.
"""


def build_config(db_state) -> dict:
    """Build sing-box config.json content from database state."""
    raise NotImplementedError("Engine layer to be refined")
