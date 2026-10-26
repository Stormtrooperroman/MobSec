# MobSec Documentation

This directory contains comprehensive guides for developing, deploying, and extending the MobSec Mobile Security Testing Platform.

## Documentation Files

### write_internal_module.md
Guide for creating **static analysis modules**.

Static modules process APK/IPA files and decompiled source code asynchronously through Redis queues. They're ideal for automated analysis tasks that don't require interactive user sessions.


### write_dynamic_module.md
Guide for creating **interactive dynamic testing modules**.

Dynamic modules enable real-time device communication through WebSocket connections. They support interactive sessions where users can issue commands and receive live feedback from running analysis tools.


### write_external_module.md
Guide for creating **external modules** that run on separate servers.

External modules communicate with the main platform through HTTP APIs and Redis, allowing modules run independently.


## Resources

- **mobsec_modules_library GitHub:** https://github.com/Stormtrooperroman/mobsec_modules_library
- **Example External Module:** https://github.com/Stormtrooperroman/external_module_example

