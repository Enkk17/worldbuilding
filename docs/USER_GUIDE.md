# User Guide

## Create the first account

Open WORLDWEAVE and choose **Create account**. Enter an email address, a password of at least 12 characters, and a display name. On a new installation, the first account is created and signed in automatically.

The default registration policy is bootstrap-only: later public sign-ups are disabled. An administrator can change `REGISTRATION_MODE` in `.env` and restart the application if broader registration is intended.

## Sign in and out

Use the sign-in page with the email and password used for registration. Choose **Sign out** to revoke the current server-side session. Signing out elsewhere or revoking sessions is not exposed in the M1 UI yet.

## Current scope

M1 establishes account access and the application foundation. Universe creation and all worldbuilding modules are being delivered through later milestones; they are not available in this build yet.
