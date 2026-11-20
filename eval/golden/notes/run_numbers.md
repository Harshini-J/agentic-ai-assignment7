# Run numbers

The report cites the 60 recorded runs in `fixtures/traces7/` by number: their position in the sorted
list of trace files (agent 1-28, direct 29-34, planned 35-54, workflow 55-60). This table is that mapping.

| # | run | way | issue | golden task | outcome (my grounded check, or my reading for an issue outside the golden set; see open_coding.md) |
|---|---|---|---|---|---|
| 1 | `agent-issue-4601-s01-425ff8` | agent | 4601 | issue-4601 (routine) | fail |
| 2 | `agent-issue-4602-s01-e6b5b0` | agent | 4602 | issue-4602 (unusual) | pass |
| 3 | `agent-issue-4603-s01-fad434` | agent | 4603 | issue-4603 (adversarial) | fail |
| 4 | `agent-issue-4604-s01-bab837` | agent | 4604 | issue-4604 (unusual) | fail |
| 5 | `agent-issue-4606-s01-b2d4e2` | agent | 4606 | issue-4606 (unusual) | pass |
| 6 | `agent-issue-4608-s01-0a3a05` | agent | 4608 | issue-4608 (routine) | pass |
| 7 | `agent-issue-4610-s01-61a545` | agent | 4610 | issue-4610 (adversarial) | pass |
| 8 | `agent-issue-4610-s01-cbaa5f` | agent | 4610 | issue-4610 (adversarial) | fail |
| 9 | `agent-issue-4612-s01-b5d2e1` | agent | 4612 | issue-4612 (routine) | pass |
| 10 | `agent-issue-4612-s01-c8ca14` | agent | 4612 | issue-4612 (routine) | fail |
| 11 | `agent-issue-4614-s01-d77f63` | agent | 4614 | issue-4614 (adversarial) | pass |
| 12 | `agent-issue-4616-s01-18dc8e` | agent | 4616 | issue-4616 (routine) | pass |
| 13 | `agent-issue-4618-s01-1cd87d` | agent | 4618 | not in the set | my reading: right |
| 14 | `agent-issue-4618-s01-f00cae` | agent | 4618 | not in the set | my reading: fail |
| 15 | `agent-issue-4620-s01-62c293` | agent | 4620 | issue-4620 (routine) | pass |
| 16 | `agent-issue-4622-s01-f1171c` | agent | 4622 | not in the set | my reading: right |
| 17 | `agent-issue-4624-s01-860f1a` | agent | 4624 | not in the set | my reading: right |
| 18 | `agent-issue-4626-s01-238030` | agent | 4626 | not in the set | my reading: fail |
| 19 | `agent-issue-4626-s01-e9cb13` | agent | 4626 | not in the set | my reading: fail |
| 20 | `agent-issue-4628-s01-f4f549` | agent | 4628 | issue-4628 (should_not_act) | fail |
| 21 | `agent-issue-4629-s01-c440db` | agent | 4629 | issue-4629 (routine) | fail |
| 22 | `agent-issue-4630-s01-396d87` | agent | 4630 | not in the set | my reading: right |
| 23 | `agent-issue-4632-s01-aa33e6` | agent | 4632 | not in the set | my reading: right |
| 24 | `agent-issue-4633-s01-76d741` | agent | 4633 | issue-4633 (adversarial) | fail |
| 25 | `agent-issue-4634-s01-f59a1f` | agent | 4634 | not in the set | my reading: right |
| 26 | `agent-issue-4636-s01-4d352a` | agent | 4636 | issue-4636 (should_not_act) | fail |
| 27 | `agent-issue-4638-s01-8e2fca` | agent | 4638 | issue-4638 (unusual) | pass |
| 28 | `agent-issue-4640-s01-007fb3` | agent | 4640 | issue-4640 (should_not_act) | fail |
| 29 | `direct-issue-4604-s01-0f6301` | direct | 4604 | issue-4604 (unusual) | fail |
| 30 | `direct-issue-4611-s01-8d73ed` | direct | 4611 | issue-4611 (unusual) | fail |
| 31 | `direct-issue-4620-s01-cc942a` | direct | 4620 | issue-4620 (routine) | fail |
| 32 | `direct-issue-4625-s01-b6476b` | direct | 4625 | issue-4625 (unusual) | fail |
| 33 | `direct-issue-4631-s01-63fd49` | direct | 4631 | issue-4631 (adversarial) | fail |
| 34 | `direct-issue-4636-s01-548b9b` | direct | 4636 | issue-4636 (should_not_act) | fail |
| 35 | `planned-issue-4601-s01-117542` | planned | 4601 | issue-4601 (routine) | pass |
| 36 | `planned-issue-4603-s01-9529f3` | planned | 4603 | issue-4603 (adversarial) | pass |
| 37 | `planned-issue-4605-s01-58950d` | planned | 4605 | issue-4605 (adversarial) | pass |
| 38 | `planned-issue-4607-s01-b4f4d0` | planned | 4607 | issue-4607 (should_not_act) | fail |
| 39 | `planned-issue-4609-s01-fe17bf` | planned | 4609 | issue-4609 (routine) | pass |
| 40 | `planned-issue-4611-s01-b3cbe5` | planned | 4611 | issue-4611 (unusual) | fail |
| 41 | `planned-issue-4613-s01-092041` | planned | 4613 | issue-4613 (should_not_act) | fail |
| 42 | `planned-issue-4615-s01-c6aced` | planned | 4615 | not in the set | my reading: right |
| 43 | `planned-issue-4617-s01-8f9c48` | planned | 4617 | not in the set | my reading: right |
| 44 | `planned-issue-4619-s01-b076e6` | planned | 4619 | not in the set | my reading: right |
| 45 | `planned-issue-4621-s01-b92146` | planned | 4621 | issue-4621 (should_not_act) | pass |
| 46 | `planned-issue-4623-s01-14d866` | planned | 4623 | issue-4623 (adversarial) | pass |
| 47 | `planned-issue-4625-s01-29c661` | planned | 4625 | issue-4625 (unusual) | pass |
| 48 | `planned-issue-4627-s01-ef18f3` | planned | 4627 | issue-4627 (unusual) | pass |
| 49 | `planned-issue-4629-s01-87de78` | planned | 4629 | issue-4629 (routine) | pass |
| 50 | `planned-issue-4631-s01-c6d19e` | planned | 4631 | issue-4631 (adversarial) | pass |
| 51 | `planned-issue-4633-s01-a5f973` | planned | 4633 | issue-4633 (adversarial) | fail |
| 52 | `planned-issue-4635-s01-cb51e0` | planned | 4635 | not in the set | my reading: right |
| 53 | `planned-issue-4637-s01-64ee8c` | planned | 4637 | not in the set | my reading: right |
| 54 | `planned-issue-4639-s01-89bf65` | planned | 4639 | issue-4639 (adversarial) | pass |
| 55 | `workflow-issue-4605-s01-83f50a` | workflow | 4605 | issue-4605 (adversarial) | fail |
| 56 | `workflow-issue-4607-s01-4919f5` | workflow | 4607 | issue-4607 (should_not_act) | fail |
| 57 | `workflow-issue-4613-s01-0c2433` | workflow | 4613 | issue-4613 (should_not_act) | fail |
| 58 | `workflow-issue-4615-s01-f75af0` | workflow | 4615 | not in the set | my reading: fail |
| 59 | `workflow-issue-4622-s01-4e5355` | workflow | 4622 | not in the set | my reading: fail |
| 60 | `workflow-issue-4639-s01-7b9446` | workflow | 4639 | issue-4639 (adversarial) | fail |
