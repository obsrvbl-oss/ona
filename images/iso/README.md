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

## References ##

1. Ubuntu's community documentation on [customizing installation CDs](https://help.ubuntu.com/community/InstallCDCustomization)
2. Detailed example preseed file:

    ```
    $ apt install installation-guide-amd64
    $ zcat /usr/share/doc/installation-guide-amd64/example-preseed.txt.gz
    ```
