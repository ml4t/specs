# Getting started

Install the package:

~~~bash
pip install ml4t-specs
~~~

Create a feed contract:

~~~python
from ml4t.specs import FeedSpec

feed = FeedSpec(
    timestamp_col="date",
    entity_col="ticker",
    close_col="settle",
    price_col="settle",
    calendar="NYSE",
    timezone="America/New_York",
    data_frequency="daily",
)
~~~

The object is independent of data-frame and execution-engine implementations. Persisted contracts
use the serialization helpers documented in the [API reference](api.md).
