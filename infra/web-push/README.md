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

## Reading the test

`tools/web-push/counts.sh` prints the live subscription count, how many of
those are on the Apple push service (iPhone, iPad or a Mac), and the
totals (subscribes, switches, renewals, unsubscribes, send runs, sends,
failures, dead endpoints removed). The 60-day read and the kill rule are in
`docs/DECISIONS.md` 0069.

## What is never here

No email, no SES, no account, no IP address kept, no user agent kept. The
function's logs hold a route, a status code and counts. The GitHub Actions
secret is the one copy of the sender token outside SSM.
