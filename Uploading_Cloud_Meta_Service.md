# How to Upload the Code to Update the Metadata to the Cloud

## Run the .venv/bin/activate

```{}
:  ~/projects/litestream ; source ~/.venv/bin/activate
```

## Test the Script Locally

For example, make sure that BigFrog can be updated.

```{}
: /home/steve/.venv ~/projects/deadstream ; ipython deadstream/update_cloud_meta.py -- --save_cloud 0 --collections BigFrog --clobber 1
```

Also try with `save_cloud 1` to make sure that works.

## Build and Tag the Docker Image using Dockerfile2

Once the script is working locally, build a docker container and tag it with `deadstream-update-cloud:latest`.

```{}
: /home/steve/.venv ~/projects/deadstream ; docker build -t deadstream-update-cloud:test -f Dockerfile2 .
: /home/steve/.venv ~/projects/deadstream ; docker tag deadstream-update-cloud:test us-central1-docker.pkg.dev/able-folio-397115/deadstream-repo/deadstream-update-cloud:latest
```

## Push the Docker Container to the Google Cloud

Authenticate:

```{}
: /home/steve/.venv ~/projects/deadstream ; ACCESS_TOKEN=$(gcloud auth print-access-token)
: /home/steve/.venv ~/projects/deadstream ; docker login -u oauth2accesstoken -p "$ACCESS_TOKEN" https://us-central1-docker.pkg.dev
: /home/steve/.venv ~/projects/deadstream ; docker push us-central1-docker.pkg.dev/able-folio-397115/deadstream-repo/deadstream-update-cloud:latest
```

Make sure that it is there, visit <https://console.cloud.google.com/artifacts/docker/able-folio-397115/us-central1/deadstream-repo?project=able-folio-397115>
