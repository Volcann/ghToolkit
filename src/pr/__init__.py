"""Alias package for ghtoolkit.pull_request providing clean `import ghtoolkit.pr` access."""

from ..pull_request import (
    DATE_FIELDS,
    DETAIL_FIELDS,
    SUMMARY_FIELDS,
    DateField,
    InlineReviewComment,
    PullRequestService,
    ReviewService,
    summarize_rest_pr,
)

__all__ = [
    "PullRequestService",
    "ReviewService",
    "DateField",
    "SUMMARY_FIELDS",
    "DETAIL_FIELDS",
    "DATE_FIELDS",
    "summarize_rest_pr",
    "InlineReviewComment",
]
