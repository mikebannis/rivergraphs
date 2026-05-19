# River Project

This is a web app for displaying river flow data.

## Local Development

To run the app locally, run:

```
$ python3 run_local.py
```

To download data, run:

```
$ python app/dl_graphs.py
```

or

```
$ python app/dl_graphs.py --verbose
```

There is also a method to download data for a specific gage:

## Deployment

Login to the prod server and:

```
$ cd /var/www/rivergraphs
$ git pull
$ sudo service apache2 restart
```

### Package install

To install a package on the server, run:

```
sudo /usr/bin/python3 -m pip install <package> --system
```
