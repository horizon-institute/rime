# RIME

This is the home of the RIME project, working towards the *Responsible Investigation of Mobile Environments*.

This is a project from the University of Nottingham, in conjunction with Telemarq.

## Quickstart for development

You'll need the following pre-installed:

* Python 3.10
* Node.js 14 or above
* NPM

If you are using Debian or Ubuntu, you can get these by running `sudo apt install python3.10 npm`. If you're using a Mac
running Homebrew, you can get them by running `brew install python@3.10 nodejs npm`. If you're using Windows with WSL,
consult the [Windows readme](README-Windows.md).

Also, you'll need to download the example phone dumps (unless you have your own). These are stored using `git lfs`. If
you'd already installed `git lfs` prior to checking out this repository, you shouldn't need to do anything; the files
would have been downloaded on checkout. Otherwise, [install `git lfs`](https://git-lfs.com/) and retrieve the examples
using `git lfs get`.

If you don't have Git LFS, you can install it on Debian or Ubuntu by running `sudo apt install git-lfs`, or, if you're
on a Mac running Homebrew, by running `brew install git-lfs`. Regardless of which system you're using, you should run
`git lfs install` if this is the first time you've used Git LFS.

RIME consists of the *rime server*, which provides the GraphQL interface and supplies any media from the device. Unless
you're just interested in making GraphQL queries, you will also want to start up a *frontend*, which provides a
Web-based application. The RIME repository ships with a suitable frontend in the `frontend` directory.

The first time you start RIME using any of the methods below, required modules will be downloaded and installed. This
will take several minutes. You'll know that RIME is ready to use when you see the Vite prompt, `Local:
http://localhost:3000/`.

### Starting the servers (Linux / Unix / Macos / Windows Subsystem for Linux)
You can run RIME directly without Docker. Set the PYTHON variable to your version of Python and run `run_dev.sh`.

	$ ./run_dev.sh

or

    $ PYTHON=python3 ./run_dev.sh

If you don't supply a Python version, `run_dev` will use `python3.10`, as this version is most compatible with third
party modules (specifically the machine-learning-related modules required for name anonymisation). At time of writing,
we recommend you stick with Python 3.10.

By default, `run_dev` will, in addition to the base requirements, install modules from
`rime/plugins/ai_requirements.txt` in order to run machine-learning-based plugins. These are not required for basic
RIME. If you want to omit them (they take up about 4.4GiB of space on for me) pass `--no-ai` to `run_dev.sh`.

### Starting the servers (Docker)
Alternatively, you can run RIME in a Docker container. The Docker Compose file exposes port 3000 to the local machine.

    $ docker compose build
	$ docker compose up

### Using the dev server

Navigate to `http://localhost:3000` in a web browser. This is the RIME frontend. RIME itself is running on a different port (port
`5001`), and the frontend will communicate with it automatically; if you don't wish to use the frontend, you can also
use a GraphQL explorer, your own GraphQL code, or simply `curl` to interact with the GraphQL endpoint at
`http://localhost:5001/graphql`.

The `run_dev` script displays another port as well. This port is used internally by the frontend technology (`vite`)
for automatic reloading during frontend development.

### Configuring RIME

Rime is configured through its YAML configuration file. If you're using `run_dev.sh`, this config file is in
`frontend/rime_settings.yaml`. However, RIME will open and use `frontend/rime_settings.local.yaml` if it exists, so you
may prefer to copy existing configuration to the `local` version if you wish to make changes.

The `filesystem.base_path` setting specifies the path where the device data
should be for the rime server to access them and serve them to the frontend.
If there are no device data under the `base_path` then the UI will
not show any available devices.

If you want to open iOS encrypted files you can do it from the frontend UI, or by adding the name of
the filesystem alongside its passphrase in the configuration file, as:

```yaml
filesystem:
  base_path: "../example/"
  passphrases:
    'ios-encrypted': 'passphrase'
```

#### Plugins

RIME supports a plugin architecture, currently in development. The only plugin you can use at the moment is `ml_names`,
which provides anonymisation of names using a derivative of [BERT](https://en.wikipedia.org/wiki/BERT_(language_model)).
To enable it, add `- ml_names` to the anonymisation configuration, like this:

    plugins:
      anonymise:
        - "ml_names"

## Contributing

Rime's official location is on Github at <https://github.com/horizon-institute/rime>. To contribute, fork this
repository and create a Github pull request.

We use Github Actions to test RIME; currently this boils down to running flake8 followed by pytest. If you would like to
run the Github Action before pushing to Github, you can use the [ACT](https://github.com/nektos/act) tool, which is very
easy to use. Install the tool, then run the actions with `act`.

## Background

The aim of the project is to provide an Open Source, extensible tool which can expose, in a useful form, the subset of
the contents of a phone appropriate for a particular investigation. The parameters of the subset might be specified in a
warrant; for example: "The parties to this investigation may view all communications between these three persons of
interest using apps A, B & C during the last 3 months, along with interactions with online service X". 

This contrasts with past practice where the *entire* set of data contained on a mobile device might be made available to
multiple parties, both constituting a disproportionate infringement of privacy and resulting in an unmanageable amount
of data for the parties concerned. 

The question RIME aims to answer is: is it possible to provide a subset of mobile device communications which is both
useful and trustworthy?

The open source and freely-available nature of RIME will ensure that its code can be inspected for correct functioning
both by all parties in an investigation and by security-focused members of the general public.  It also ensures that it
can be extended to include data from other applications and platforms.

The RIME software assumes that an unencrypted dump of the filesystem of each device can be obtained.  

For iOS devices, this can be done using the backup facilities available in the Mac Finder. Make sure that the option to
'Encrypt local backup' is disabled! For iOS devices RIME supports encrypted backups as well, however you should provide
the passphrase to decrypt the backup.

For Android devices...  (TBD)

RIME can examine the filesystems of multiple devices simultaneously, and merge their results into a single timeline.

## Concepts

Some terminology you will come across when using, and especially when developing for, RIME:

Filesystem : This is a copy of a device's filesystem, which needs to be placed in a subdirectory on the machine running
RIME.  If you have multiple filesystem dumps, they can be put in side-by-side subdirectories.  These might come from
multiple devices used by a single person, or from multiple users.  The RIME software makes the contents of these
filesystems available to 'Providers'.

Provider : Any app or platform that can provide data for RIME queries. 'AndroidWhatsApp' is one provider. 'IOSContacts'
is another.  The system can query the providers found on a particular filesystem, and each one will return any relevant
data in its filesystem.  Often the results will be a set of 'Events'.

Event : An Event is an entry in a provider's data that occurred *at a particular time*.  Subclasses like 'MessageEvent'
add extra fields, such as the sender of a message.

So a typical RIME query involves asking all of the Providers on all of the Filesystems for the MessageEvents they have
that match certain criteria, and then presenting the results on a timeline.

### Subsets

The parties in an investigation will generally be given a subset of the data containing only the information pertinent
to their enquiry.  RIME is therefore able to take a particular query such as 'All of the messages sent by Alice between
1st Jan and 31st March' and create a new Filesystem mimicing the original but containing only the relevant data.

That subset can then be given to another RIME user and queried in the same way as the original.

## Licence

This software is distributed under the terms of the GNU GENERAL PUBLIC LICENSE v3.
See LICENSE.txt for more information.

