---
name: seed-expenses
description: Seed realistic dummy expenses for a specific user. Accept a user ID, expense count, and number of past months.
---

Read `database/db.py` to understand the expenses table schema, the database connection pattern, and the database file name.

The user invoking this skill should provide three inputs:

- `user_id` — integer ID of the user
- `count` — integer number of expenses to create
- `months` — integer number of past months to spread them across

For example:

`$seed-expenses user_id=1 count=50 months=6`

If any argument is missing or is not a valid integer, stop and ask the user to provide the missing or invalid value.

## Step 1 — Parse inputs

Extract the following from the user's request:

- `user_id` — integer
- `count` — integer, number of expenses to create
- `months` — integer, how many past months to spread them across

Do not begin modifying the database until all three values are available and valid.

## Step 2 — Verify user exists

Before generating anything, confirm that `user_id` exists in the users table.

If the user does not exist, stop and report:

`No user found with id <user_id>.`

Do not create any expenses in this case.

## Step 3 — Generate and insert expenses

Write and run a Python script that:

1. Spreads the requested number of expenses randomly across the past `months` months.

2. Uses the following categories with realistic Indian descriptions and amounts (₹):

   - Food: ₹50–₹800
   - Transport: ₹20–₹500
   - Bills: ₹200–₹3000
   - Health: ₹100–₹2000
   - Entertainment: ₹100–₹1500
   - Shopping: ₹200–₹5000
   - Other: ₹50–₹1000

3. Distributes categories roughly proportionally:
   - Food should be the most common.
   - Health and Entertainment should be among the least common.

4. Uses the database connection pattern from `database/db.py`.
   Do not hardcode the database filename.

5. Uses parameterized SQL queries only.
   Do not use string formatting or interpolation to construct SQL queries.

6. Inserts all expenses in a single transaction.
   If any insert fails, roll back the entire transaction.

Ensure all generated records conform to the actual expenses table schema found in `database/db.py`.

## Step 4 — Confirm

After successfully inserting the expenses, print:

- How many expenses were inserted
- The date range the generated expenses span
- A sample of 5 inserted records