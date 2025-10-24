import requests
import pandas as pd
from pprint import pprint
import matplotlib.pyplot as plt
from datetime import datetime as dt

start = dt.now()

data = {
    "sort": "TimeStamp-desc",
    "date": "2022-03-06",
    "endDate": "2022-07-11",
}
r = requests.post("https://seoflow.wyo.gov/Data/DatasetGrid?dataset=4578", data=data)

mid = dt.now()
print(f"made request in {mid - start}")
print(f' got {len(r.json()["Data"])} data points')

print(r)
# pprint(r.request.body)
# pprint(r.content)

df = pd.DataFrame(r.json()["Data"])
print(df.head())
df.TimeStamp = pd.to_datetime(df.TimeStamp, format="%Y-%m-%d %H:%M:%S")
mid2 = dt.now()

print(f"made df in {mid2 - mid}")

# df.Value.plot()

plt.plot(df.TimeStamp, df.Value)
plt.show()
print(f"made plot in {dt.now() - mid2}")
