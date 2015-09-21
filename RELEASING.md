# Releasing a new version

This is a document that describes the steps to take in order to make a new
release of the ONA. Parts of this may become automated.

* [ ] Bring in all the latest changes as a PR in the
      https://github.com/obsrvbl/ona repository
  * [ ] Include relevant changes in CHANGELOG.md
  * [ ] Bump the VERSION in the Makefile
  * [ ] Verify README.md is up-to-date
  * [ ] Validate on all supported platforms

* [ ] Once merged make sure to create all the relevant branches and tags
  * [ ] major releases get a branch M.x
  * [ ] every release gets a tag like vM.m.p

* [ ] Make sure the appropriate images are built
  * [ ] Docker (available on Docker Hub)
  * [ ] ISO (available via S3 download)
  * [ ] AMI (available via Amazon Marketplace)
