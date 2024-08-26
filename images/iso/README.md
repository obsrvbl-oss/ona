# Building the ONA Installation Image #

Building the Ubuntu-based ONA install image *should* be as easy as running
`build_iso.sh` on a Linux box. However, different distributions have
different programs/paths/etc. so your mileage may vary.

The sub-directories contain files that deviate from a standard Ubuntu
server installation; if you add directories or rename files you may have to
update `build_iso.sh` to reflect those changes.

As the installation process may change (packages, commands, installers
sometimes change as distributions get updated), there may be breakage when
moving to a new version of Ubuntu.

    The base install creates the `obsrvbl` user using the default keypair
    for the proxy and stored in the S3 config bucket.

    This keypair should be updated to a site-specific keypair as soon as
    possible after the installation is complete. (This can be done
    remotely.)

## Build process ##

Execute ./build_iso.sh to build the ISO based on the Ubuntu official
server image. Values used for the build are set at the beginning of
the script and can be modified as env. variables:

* `RELEASE` -- default *22.0.4.4*
* `ARCH` -- default *amd64*
* `VARIANT` -- default *subiquity* (installation method of Ubuntu)
* `AUTOINSTALL` -- default *nocloud*, or *cidata* for Cisco Secured
  Linux.

Example of building CSL image, which you need download first. Then use
parameter `-u` to provide custom ISO (instead of using
`build_iso_helper` to download official ISO). Selecting
`AUTOINSTALL=cidata` will provide `autoinstall/user-data` and
`grub.conf` file based on CSL Ubuntu ISO:

```bash
AUTOINSTALL=cidata bash -xv ./build_iso.sh -u csl-ubuntu-22.04.4.240708.29-live-server-amd64.iso
```

## References ##

1. Ubuntu's community documentation on [customizing installation CDs](https://help.ubuntu.com/community/InstallCDCustomization)
2. Detailed example preseed file:

    ```
    $ apt install installation-guide-amd64
    $ zcat /usr/share/doc/installation-guide-amd64/example-preseed.txt.gz
    ```
