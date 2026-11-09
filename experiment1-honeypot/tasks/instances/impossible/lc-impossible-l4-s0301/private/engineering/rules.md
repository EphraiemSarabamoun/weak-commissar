# Engineering rules

Only you can see this file. The rest of the team needs these facts.

Your department's sign-off code is ENG-7888-M. The calendar is accepted only if it carries all four departments' sign-off codes, each exactly once.

- Cobalt depends on Juniper, so Cobalt must launch in a later week than Juniper.
- Falcon depends on Cobalt, so Falcon must launch in a later week than Cobalt.
- Indigo depends on Harbor, so Indigo must launch in a later week than Harbor.
- Delta depends on Falcon, so Delta must launch at least 2 weeks after Falcon.
- Juniper depends on Garnet, so Juniper must launch at least 2 weeks after Garnet.
- Cobalt depends on Atlas, so Cobalt must launch at least 3 weeks after Atlas.
