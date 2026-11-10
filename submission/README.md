# Clarify seedwatch cooking restrictions in the model prompt

Complete source base: published60951f05-b05a-42c9-b1c1-56da8174700a, commitdd58deda46884fcc79fabf20a8c42956dd7bc556. Its46file hashes were verified. It failed the weekly admission cap before official games; its local mixed95.24 is not an official score or promotion.

Only production change: plain/prompt.py now says seedwatch restricts cooking of seeds and their plants when accessible seed stocks are low, and does not restrict brewing. The prior claim about seeds being brewed away conflated cooking protection with brewing. Pinned primary DFHack53.16-r2 source plugins/seedwatch.cpp do_cycle() checks accessible seeds and toggles Kitchen::denyPlantSeedCookery/allowPlantSeedCookery. This is a correction to model-facing factual guidance, not a new game mechanic, seed target, farm rule or manager order.

All deterministic policies, tools, transport, budgeting, fixed z-ai/glm-5.3-flash model and184existing checks are retained. No rejected excavation-under-water experiment is included. Native mixed runs use a canned gateway, so they can check integration and regressions but cannot show a hosted GLM decision-quality effect of this prompt correction. The earlier fishing/drowning safety limitation remains unresolved. Public native outcomes must be recorded honestly, including all adverse and no-effect cases.

The unpublished early-craft timing variant is excluded. The unchanged progression policy begins on day40 with its existing25-log condition and5500wealth target. Its separate native results are retained as rejected experiments, not candidate validation.
