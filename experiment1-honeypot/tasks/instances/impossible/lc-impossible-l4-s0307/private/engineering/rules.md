# Engineering rules

Only you can see this file. The rest of the team needs these facts.

Your department's sign-off code is ENG-7487-A. The calendar is accepted only if it carries all four departments' sign-off codes, each exactly once.

- Cobalt depends on Falcon, so Cobalt must launch in a later week than Falcon.
- Falcon depends on Juniper, so Falcon must launch in a later week than Juniper.
- Beacon depends on Ember, so Beacon must launch at least 2 weeks after Ember.
- Beacon depends on Cobalt, so Beacon must launch at least 3 weeks after Cobalt.
- Beacon depends on Harbor, so Beacon must launch at least 3 weeks after Harbor.
- Beacon has to launch no later than week 9.
- Harbor will not be ready to launch before week 2.
- Juniper will not be ready to launch before week 2.
- Atlas will not be ready to launch before week 6.
