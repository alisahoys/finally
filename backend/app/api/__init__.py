"""REST API routes.

Reads are plain `def` so FastAPI runs them in a worker thread. Writes are `async`
because they also change what the market data source tracks (see app.services).
"""
