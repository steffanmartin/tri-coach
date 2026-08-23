FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image ships a dl.yarnpkg.com apt source with an untrusted/missing
# GPG key (NO_PUBKEY 62D54FD4003F6525), which breaks `apt-get update` for
# every feature installer that runs after it (e.g. common-utils). The node
# feature below installs its own yarn via corepack, so drop this stale source.
RUN rm -f /etc/apt/sources.list.d/yarn.list
