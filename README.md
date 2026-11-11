# Cincinnati / Hamilton County, OH — Code Enforcement Leads

Built like `cleveland-code-enforcement` and `columbus-code-enforcement`.

- **Cases:** City of Cincinnati Open Data *Code Enforcement* (`data.cincinnati-oh.gov/d/cncm-znd6`,
  refreshed daily; also covers Norwood, Forest Park, Sycamore Twp and Blue Ash). Open cases, plus
  cases closed in the last year where the owner didn't fix or pay (costs put on the tax bill,
  owner billed, sent to the Abandoned Property Program).
- **Owners:** CAGIS quarterly Hamilton County parcel file — owner, mailing address, parcel,
  value, county foreclosure flag, delinquent taxes.

One lead per property, scored 0–100 (demolition / vacant building highest; trash and weeds lowest;
bonuses for multiple cases, age, unpaid city costs, out-of-state or individual owners, foreclosure
flag, delinquent taxes). Trash set-outs, recycling, trees and graffiti are ignored.

Outputs: `docs/index.html` dashboard · `docs/cincinnati_code_enforcement.json` (read by
ohio-lead-stacker) · `data/ghl_cincinnati_code_enforcement.csv` (score 40+, owner found).
