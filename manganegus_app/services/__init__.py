"""
MangaNegus Services Module

Provides various services for the application:
- DiscoveryService: MangaDex-first discovery with Jikan fallback
"""

from .discovery_service import DiscoveryService, get_discovery_service

__all__ = ['DiscoveryService', 'get_discovery_service']
