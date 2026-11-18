## Packaging

Phonotype is packaged for Gentoo only; the ebuild lives in the
[`deepbadger` overlay](https://github.com/deepbadger/gentoo-overlay)
(`app-accessibility/phonotype`) and installs from the release tag's source archive.

Files here are installed by that ebuild:

- `phonotype-ydotoold` – starts `ydotoold` with the per-user socket
- `phonotype-tray.service`, `ydotoold.service` – systemd user units (`USE=systemd`, not tested)
- `99-uinput.rules` – udev rule giving the `input` group access to `/dev/uinput`

The OpenRC user services are kept in the overlay (`files/*.user-initd`).
