from abc import ABC, abstractmethod

class ServiceClient(ABC):
    """Abstract interface that all service config objects must implement.

    Each service should implement a simple `ping()` method so the caller can
    check availability. Service-specific construction/validation is performed
    in the individual classes' __init__.
    """

    @abstractmethod
    def ping(self) -> bool:
        """Check if the service is reachable."""


class ServiceException(Exception):
    """Custom exception for Prometheus API errors."""

    def __init__(self, message: object = None, explanation: object = None):
        """Provide additional exception explanation"""
        self.explanation = explanation
        self.message = message
        super(ServiceException, self).__init__(message)

    def __str__(self):
        message = super(ServiceException, self).__str__()
        if self.explanation:
            message = f"{message}: {self.explanation}"
        return message

#Implement an IPMI service client besides prometheus

class Service:
    pass