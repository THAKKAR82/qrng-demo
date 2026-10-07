# Vendored fonts: IBM Plex

These are IBM Plex fonts, self-hosted so the app needs no network. They are licensed under the SIL Open Font License 1.1; the full text is in [`LICENSE.txt`](LICENSE.txt), next to the font files.

They are IBM's own "split" web subsets (Latin-1 and Pi, which holds symbols such as ∞, ≈, ×, ±, → and ₂), copied unmodified from IBM's npm packages:

| Package | Version | Source |
|---|---|---|
| `@ibm/plex-sans` | 1.1.0 | https://registry.npmjs.org/@ibm/plex-sans/-/plex-sans-1.1.0.tgz, path `package/fonts/split/woff2/` |
| `@ibm/plex-mono` | 2.5.0 | https://registry.npmjs.org/@ibm/plex-mono/-/plex-mono-2.5.0.tgz, path `package/fonts/split/woff2/` |

The project is https://github.com/IBM/plex. On 2026-10-06 every file here was compared byte for byte with the files in those tarballs, and all were identical. Their SHA-256 hashes:

| File | SHA-256 |
|---|---|
| `IBMPlexMono-Medium-Latin1.woff2` | `41201b658a328b9d00368215c2f1102770f80b15952ab82631e4006255e6365d` |
| `IBMPlexMono-Medium-Pi.woff2` | `92bd18415e8c43a2569f615e4e84a94b1b1c4e0377ba9d8f4d894bbf6ffcc39d` |
| `IBMPlexMono-Regular-Latin1.woff2` | `e8993d946649b9d01abb1ed06d574b19d8ea3e66b5c3948602db335c44c18e56` |
| `IBMPlexMono-Regular-Pi.woff2` | `b8002770aa636f544ba43e124da6a227301769754f295eae26e16475b469c767` |
| `IBMPlexSans-Medium-Latin1.woff2` | `b5610af04d0d4b5a14a621d96d974b993e945a065db1a8861918f69ef9321934` |
| `IBMPlexSans-Medium-Pi.woff2` | `bf05f10c977353cfb5a5c11e8973adf77c2b93a4798da3aa0dd8ba5088e12515` |
| `IBMPlexSans-Regular-Latin1.woff2` | `b5ad7bd39f996144915f0ad9849a90183b27d8c28ad97ed98af5b1bebc51f6b1` |
| `IBMPlexSans-Regular-Pi.woff2` | `1487059829a180f975627e473acc81ff22c2c0faf1da09b314c27eeb41b7f2e4` |
| `IBMPlexSans-SemiBold-Latin1.woff2` | `fff0ab3a88b0b4aa0b693e4f0201359a15183b08e3fa5696d1918d8f0ade8ad5` |
| `IBMPlexSans-SemiBold-Pi.woff2` | `768421433d850d3a30118dddf05972625d99ee49bc32c5a8fd26bbe020c4d0f9` |

`LICENSE.txt` is the `LICENSE.txt` shipped in both packages (they are the same), except for one trailing space that the repository's whitespace hook removes.

To re-check, run `shasum -a 256 *.woff2` here and compare with the table, or with the files in the tarballs above. Do not replace these files with other versions or with your own subsets without updating this note.
