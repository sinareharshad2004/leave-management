from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Page-number pagination: ?page=2&page_size=20 (max 100)."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
