# Web push service (DECISIONS 0069)

The one piece of Trout Truck that is not a static file: a Lambda behind a
function URL, a DynamoDB table and four SSM parameters, all in Trout Truck's
own AWS member account (`trouttruck`). The provider's `allowed_account_ids`
refuses any other account.

- `lambda/`: the function. `handler.mjs` is the logic (tested by
  `make pushlambda`, no AWS needed); `dynamo.mjs` the table; `index.mjs` the
  wiring; `validate.mjs` what is accepted. `web-push` is the one npm
  dependency.
- `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`: the resources.
  `make pushinfra` validates them without reading state or touching an account.
- `../../pipeline/src/cfpa/push.py`: the pipeline side (the diff and the two
  workflow commands). `../../tools/web-push/counts.sh`: the read.

## Owner steps, in order

Nothing below is run by an agent. Every command runs as the `trouttruck`
account (for example through `_agent-tools/aws-as-trouttruck.sh`, or an AWS
profile for it).

1. Install the function's one dependency, which Terraform zips:

       cd infra/web-push/lambda && npm ci --omit=dev && cd ..

2. Generate the VAPID key pair once (prints a public and a private key;
   neither is ever committed):

       npx --package web-push@3.6.7 web-push generate-vapid-keys

3. Put the four parameters in SSM. The two secrets are SecureStrings under
   the account's default `aws/ssm` key. Keep the sender token for step 5.

       aws ssm put-parameter --name /trout-truck/web-push/vapid-public-key --type String --value '<public key>'
       aws ssm put-parameter --name /trout-truck/web-push/vapid-private-key --type SecureString --value '<private key>'
       aws ssm put-parameter --name /trout-truck/web-push/vapid-subject --type String --value 'mailto:chelsea@chelseakr.com'
       aws ssm put-parameter --name /trout-truck/web-push/sender-token --type SecureString --value "$(openssl rand -base64 48 | tr -d '\n')"

4. Create the table, the function and its URL. Review the plan before `yes`.

       terraform init
       terraform apply -var aws_account_id=266294231534 -var site_origin=https://trouttruck.com

   `terraform output function_url` prints the URL for the next step.

5. Give the publish workflow the three values. The first two are public and
   are repository variables; the token is a secret.

       gh variable set PUSH_API_URL --body '<function_url, no trailing slash>'
       gh variable set PUSH_VAPID_PUBLIC_KEY --body '<public key>'
       aws ssm get-parameter --with-decryption --name /trout-truck/web-push/sender-token --query Parameter.Value --output text | gh secret set PUSH_SENDER_TOKEN

6. Run the publish workflow (`gh workflow run publish.yml`) or wait for the
   next scheduled run. The "Alert me about this water" control appears in
   the calendar box of every California and Tennessee water page, and the
   privacy page gains its section.

To turn it off: unset the two variables (`gh variable delete ...`) and the
next publish builds the site without any of it. The service can stay up at
about $0 a month, or `terraform destroy` removes it.

## Limits on the open routes (DECISIONS 0074)

`/subscribe` and `/unsubscribe` take no token, so the function bounds them
itself (`LIMITS` in `lambda/handler.mjs`):

| Limit | Value |
|---|---|
| Calls to the two routes from one network, per UTC day | 20 |
| New subscriptions from everyone, per UTC day | 100 |
| Live subscriptions on one water | 100 |
| Live subscriptions in all | 2,000 |
| Body of a browser's call | 4 KB |
| Refusals in a row (400, 401, 403) before a subscription is removed | 3 |
| Time one `/send` call keeps starting deliveries | 90 s |

Over a limit the answer is 429 with `Retry-After`. The per-network count is
kept under a keyed code of the address and the day, never the address, in a
row that expires a day later. The table also has a ceiling on its request
units per second (`table_max_write_units`, `table_max_read_units`), so its
monthly cost has a known maximum.

### Applying a change to the function or the table

After the pull request that carries the change is merged and a publish has
run (so the privacy page describes the limits before the service applies
them), as the `trouttruck` account, from an up-to-date `main`:

    cd infra/web-push/lambda && npm ci --omit=dev && cd ..
    terraform init
    terraform plan -var aws_account_id=266294231534 -var site_origin=https://trouttruck.com

The plan for the 0074 change should show two resources changed in place and
nothing destroyed: the function (new code) and the table (the request-unit
ceilings on it and on `by_water`). Pass the same `-var` values as the first
apply (`budget_email` and `reserved_concurrency` too, if they were set), then
`terraform apply` with them. `budget_email` is worth setting if it is not:
it is the one warning when the account's spend passes $4 in a month.

Check afterwards: `tools/web-push/counts.sh` still prints the totals, and
"Alert me about this water" on a water page still turns on and off.

## Reading the test

`tools/web-push/counts.sh` prints the live subscription count, how many of
those are on the Apple push service (iPhone, iPad or a Mac), and the
totals (subscribes, switches, renewals, unsubscribes, send runs, sends,
failures, dead endpoints removed, deliveries skipped for time). The 60-day read and the kill rule are in
`docs/DECISIONS.md` 0069.

## What is never here

No email, no SES, no account, no IP address kept, no user agent kept. The
per-network limit keeps a keyed code and a count for a day (above), not the
address. The function's logs hold a route, a status code and counts. The GitHub Actions
secret is the one copy of the sender token outside SSM.
