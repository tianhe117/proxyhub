"""Data access layer for ProxyHub.

子模块一表一文件（node / inbound / outbound / service / subscription），
调用方直接 `from app.db.<table> import <fn>`；本包不做聚合导出。
"""
