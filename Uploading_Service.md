# How to Upload the Code in this Branch to the Google Cloud

## Run the .venv/bin/activate

```{}
:  ~/projects/litestream ; source ~/.venv/bin/activate
```

## Make Sure that I have permission to run Docker commands

```{}
sudo usermod -aG docker $USER
exec su -l $USER
```

: /home/steve/.venv ~/projects/deadstream ; newgrp docker

## Create the image and upload it to Google Cloud Artifactory

### Create an artifactory location for this project.

`: /home/steve/myenv ~/projects/deadstream ; gcloud builds submit --tag gcr.io/able-folio-397115/deadstream`

### Verify That the Repo is on the Cloud

```{}

: /home/steve/myenv ~/projects/deadstream ; gcloud artifacts repositories list
Listing items under project able-folio-397115, location us-central1.

                                                                                  ARTIFACT_REGISTRY
REPOSITORY               FORMAT  MODE                 DESCRIPTION                        LOCATION     LABELS  ENCRYPTION          CREATE_TIME          UPDATE_TIME          SIZE (MB)
cloud-run-source-deploy  DOCKER  STANDARD_REPOSITORY  Cloud Run Source Deployments       us-central1          Google-managed key  2023-12-17T18:27:01  2023-12-17T18:27:01  0
deadstream-repo          DOCKER  STANDARD_REPOSITORY  Docker repo for Deadstream images  us-central1          Google-managed key  2025-08-24T17:04:40  2025-08-24T17:04:40  0
quickstart-python-repo   PYTHON  STANDARD_REPOSITORY  Python package repository          us-central1          Google-managed key  2023-12-19T17:38:01  2023-12-21T17:40:15  0.875
```

### Setup Permissions to Write to This Repo

```{}
: /home/steve/myenv ~/projects/deadstream ; gcloud artifacts repositories add-iam-policy-binding deadstream-repo \
  --location=us-central1 \
  --project=able-folio-397115 \
  --member="user:steve@spertilo.net" \
  --role="roles/artifactregistry.writer"
```

### Build the Docker Image

`: /home/steve/myenv ~/projects/deadstream ; docker build -t us-central1-docker.pkg.dev/able-folio-397115/deadstream-repo/deadstream:latest .`

### Upload the Image to the Cloud

`: /home/steve/myenv ~/projects/deadstream ; docker push us-central1-docker.pkg.dev/able-folio-397115/deadstream-repo/deadstream:latest`

### Verify that the Image has been uploaded to the artifact registry

See https://console.cloud.google.com/artifacts?chat=true&invt=Ab6V3Q&project=able-folio-397115

### Other Useful Commands

```{}
: /home/steve/.venv ~/projects/deadstream ; docker image ls
REPOSITORY                                                                TAG       IMAGE ID       CREATED         SIZE
us-central1-docker.pkg.dev/able-folio-397115/deadstream-repo/deadstream   latest    c97f2494ba17   5 minutes ago   1.08GB
hello-world                                                               latest    1b44b5a3e06a   2 weeks ago     10.1kB
```

### Build a Test Docker Image

```{}
: /home/steve/.venv ~/projects/deadstream ; docker build -t test .
: /home/steve/.venv ~/projects/deadstream ; docker run --rm -it test /bin/bash
then
root@09a3a630d371:/app# flask --app deadstream/app.py run --host 0.0.0.0 --port 8080
```


## Running the Service in CloudRun

See https://console.cloud.google.com/run?invt=Ab6V4w&project=able-folio-397115&supportedpurview=project to give an overview of the containers that we know of.

Click `Edit and deploy new revision`, at the top of the screen, to modify the running service (that is connected to the URL in the code).
I have modified the current version to be drastically simpler. But it doesn't upload the results to the cloud, which will drastically reduce cost.

## Cleaning up Docker Images, etc

`: /home/steve/.venv ~/projects/deadstream ; docker system prune -a --volumes` cleans up cached images and containers.

`: /home/steve/.venv ~/projects/deadstream ; docker image prune`

and the classic: `: /home/steve/.venv ~/projects/deadstream ; docker image ls` and `: /home/steve/.venv ~/projects/deadstream ; docker rmi <image>`

