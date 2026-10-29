# Demo people

Real people who agreed to act as test applicants. Each has their own folder with:

- `photo.jpg`: the passport-style photo the card and the registry face come from.
- `person.json`: the details typed into the KYC form. Fields listed under `placeholders` are made up for the demo, not the person's real details.
- `card_preview.jpg`: what their card looks like. **It is only a preview:** its QR was signed on the author's machine, so it won't verify on yours.

## Make the cards on your machine

The QR on a card is signed with the local demo issuer key, which is never committed. So make the cards where you run TrueID:

```bash
.venv/Scripts/python.exe scripts/make_person_card.py --all     # Linux/mac: .venv/bin/python
```

This writes `data/generated/people/<slug>/card.jpg` and `details.json`, and enrols each person in the demo identity, tax, telecom, CKYC and credit registries. It also gives each person a consistent simulated digital footprint. `scripts/build_all.sh` runs it at the end of a full build. Restart the backend afterwards.

Then apply at `/kyc`:

1. Upload `card.jpg`.
2. Type the values from `details.json`.
3. Take a **live** selfie and do the head-turn check. A photo of the photo is caught as a reused picture.

Every required check should pass, and the case is approved once liveness passes.

## Add a person

Make a folder `demo/people/<slug>/` with `photo.jpg` and a `person.json` like the existing one. Only `name`, `dob` (DD/MM/YYYY) and `gender` (M/F) are required; anything else left empty is generated the same way every time. Or run it once from the command line:

```bash
.venv/Scripts/python.exe scripts/make_person_card.py --photo photo.jpg --name "Full Name" --dob 01/01/2000 --gender M
```

Only add people who have agreed: this repository is public.
