# Copyright 2012-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Supporting infrastructure for Piston-based APIs in MAAS."""

__all__ = [
    'admin_method',
    'AnonymousOperationsHandler',
    'operation',
    'OperationsHandler',
    ]

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404
from maasserver.api.doc import get_api_description_hash
from maasserver.exceptions import MAASAPIBadRequest
from piston3.authentication import NoAuthentication
from piston3.emitters import Emitter
from piston3.handler import (
    AnonymousBaseHandler,
    BaseHandler,
    HandlerMetaClass,
)
from piston3.resource import Resource
from piston3.utils import (
    HttpStatusCode,
    rc,
)
from provisioningserver.logger import LegacyLogger


log = LegacyLogger()


class OperationsResource(Resource):
    """A resource supporting operation dispatch.

    All requests are passed onto the handler's `dispatch` method. See
    :class:`OperationsHandler`.
    """

    crudmap = Resource.callmap
    callmap = dict.fromkeys(crudmap, "dispatch")

    @staticmethod
    def _use_emitter(result):
        """Override to force piston to the correct thing with Dango >=1.7."""
        # Always return False because we don't want Pison to do the wrong
        # thing with the content in HttpResponse objects. (Django 1.7 removed
        # the _base_content_is_iter attribute so there is no way to identify
        # the content inside of the response.) This means we never want Piston
        # to use its emitter on the contents inside of an HttpResponse.
        return False

    def __call__(self, request, *args, **kwargs):
        upcall = super(OperationsResource, self).__call__
        response = upcall(request, *args, **kwargs)
        response["X-MAAS-API-Hash"] = get_api_description_hash()
        return response

    def error_handler(self, e, request, meth, em_format):
        """
        Override piston's error_handler to fix bug #1228205 and generally
        do not hide exceptions.
        """
        if isinstance(e, Http404):
            return rc.NOT_FOUND
        elif isinstance(e, HttpStatusCode):
            return e.response
        else:
            raise

    @property
    def is_authentication_attempted(self):
        """Will use of this resource attempt to authenticate the client?

        For example, `None`, ``[]``, and :class:`NoAuthentication` are all
        examples of authentication handlers that do *not* count.
        """
        return len(self.authentication) != 0 and not any(
            isinstance(auth, NoAuthentication) for auth in self.authentication)


class RestrictedResource(OperationsResource):
    """A resource that's restricted to active users."""

    def __init__(self, handler, *, authentication):
        """A value for `authentication` MUST be provided AND be meaningful.

        This prevents the situation where none of the following are restricted
        at all::

          handler = RestrictedResource(HandlerClass)
          handler = RestrictedResource(HandlerClass, authentication=None)
          handler = RestrictedResource(HandlerClass, authentication=[])

        """
        super(RestrictedResource, self).__init__(handler, authentication)
        if not self.is_authentication_attempted:
            raise AssertionError("Authentication must be attempted.")

    def authenticate(self, request, rm):
        actor, anonymous = super(
            RestrictedResource, self).authenticate(request, rm)
        if not anonymous and not request.user.is_active:
            raise PermissionDenied("User is not allowed access to this API.")
        else:
            return actor, anonymous


class AdminRestrictedResource(RestrictedResource):
    """A resource that's restricted to administrators."""

    def authenticate(self, request, rm):
        actor, anonymous = super(
            AdminRestrictedResource, self).authenticate(request, rm)
        if anonymous or not request.user.is_superuser:
            raise PermissionDenied("User is not allowed access to this API.")
        else:
            return actor, anonymous


def operation(idempotent, exported_as=None):
    """Decorator to make a method available on the API.

    :param idempotent: If this operation is idempotent. Idempotent operations
        are made available via HTTP GET, non-idempotent operations via HTTP
        POST.
    :param exported_as: Optional operation name; defaults to the name of the
        exported method.
    """
    method = "GET" if idempotent else "POST"

    def _decorator(func):
        if exported_as is None:
            func.export = method, func.__name__
        else:
            func.export = method, exported_as
        return func

    return _decorator


METHOD_RESERVED_ADMIN = "This method is reserved for admin users."


def admin_method(func):
    """Decorator to protect a method from non-admin users.

    If a non-admin tries to call a method decorated with this decorator,
    they will get an HTTP "forbidden" error and a message saying the
    operation is accessible only to administrators.
    """

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied(METHOD_RESERVED_ADMIN)
        else:
            return func(self, request, *args, **kwargs)
    return wrapper


class OperationsHandlerType(HandlerMetaClass):
    """Type for handlers that dispatch operations.

    Collects all the exported operations, CRUD and custom, into the class's
    `exports` attribute. This is a signature:function mapping, where signature
    is an (http-method, operation-name) tuple. If operation-name is None, it's
    a CRUD method.

    The `allowed_methods` attribute is calculated as the union of all HTTP
    methods required for the exported CRUD and custom operations.
    """

    def __new__(metaclass, name, bases, namespace):
        cls = super(OperationsHandlerType, metaclass).__new__(
            metaclass, name, bases, namespace)

        # Create a signature:function mapping for CRUD operations.
        crud = {
            (http_method, None): getattr(cls, method)
            for http_method, method in list(OperationsResource.crudmap.items())
            if getattr(cls, method, None) is not None
            }

        # Create a signature:function mapping for non-CRUD operations.
        operations = {
            attribute.export: attribute
            for attribute in list(vars(cls).values())
            if getattr(attribute, "export", None) is not None
            }

        # Create the exports mapping.
        exports = {}

        # Add parent classes' exports if they still correspond to a valid
        # method on the class we're considering. This allows subclasses to
        # remove methods by defining an attribute of the same name as None.
        for base in bases:
            for key, value in vars(base).items():
                export = getattr(value, "export", None)
                if export is not None:
                    new_func = getattr(cls, key, None)
                    if new_func is not None:
                        exports[export] = new_func

        # Export custom operations.
        exports.update(operations)

        # Check that no CRUD methods have been marked as operations (i.e.
        # those that are used via op=name). This causes (unconfirmed) weird
        # behaviour within Piston3 and/or Django, and is plain confusing
        # anyway, so forbid it.
        methods_exported = {method for http_method, method in exports}
        for http_method, method in OperationsResource.crudmap.items():
            if method in methods_exported:
                raise AssertionError(
                    "A CRUD operation (%s/%s) has been registered as an "
                    "operation on %s." % (http_method, method, name))

        # Export CRUD methods.
        exports.update(crud)

        # Update the class.
        cls.exports = exports
        cls.allowed_methods = frozenset(
            http_method for http_method, name in exports)

        # Flags used later.
        has_fields = cls.fields is not BaseHandler.fields
        has_resource_uri = hasattr(cls, "resource_uri")
        is_internal_only = cls.__module__ in {__name__, "metadataserver.api"}

        # Reject handlers which omit fields required for self-referential
        # URIs. See bug 1643552. We ignore handlers that don't define `fields`
        # because we assume they are doing custom object rendering and we have
        # no way to check here for compliance.
        if has_fields and has_resource_uri:
            _, uri_params, *_ = cls.resource_uri()
            missing = set(uri_params).difference(cls.fields)
            if len(missing) != 0:
                raise OperationsHandlerMisconfigured(
                    "{handler.__module__}.{handler.__name__} does not render "
                    "all fields required to construct a self-referential URI. "
                    "Fields missing: {missing}.".format(
                        handler=cls, missing=" ".join(sorted(missing))))

        # Piston uses `resource_uri` even for handlers without models in order
        # to generate documentation. We ignore those modules we consider "for
        # internal use only" since we do not intend to generate documentation
        # for these.
        if not has_resource_uri and not is_internal_only:
            log.warn(
                "{handler.__module__}.{handler.__name__} does not have "
                "`resource_uri`. This means it may be omitted from generated "
                "documentation. Please investigate.", handler=cls)

        return cls


class OperationsHandlerMisconfigured(Exception):
    """Handler has been misconfigured; see the error message for details."""


class OperationsHandlerMixin:
    """Handler mixin for operations dispatch.

    This enabled dispatch to custom functions that piggyback on HTTP methods
    that ordinarily, in Piston, are used for CRUD operations.

    This must be used in cooperation with :class:`OperationsResource` and
    :class:`OperationsHandlerType`.
    """
    # CSRF protection is on by default.  Only pure 0-legged oauth API requests
    # don't go through the CSRF machinery (see
    # middleware.CSRFHelperMiddleware).
    # This is a field used by piston to decide whether or not CSRF protection
    # should be performed.
    csrf_exempt = False

    # Populated by OperationsHandlerType.
    exports = None

    # Specified by subclasses.
    anonymous = None

    def dispatch(self, request, *args, **kwargs):
        op = request.GET.get("op") or request.POST.get("op")
        signature = request.method.upper(), op
        function = self.exports.get(signature)
        if function is None:
            raise MAASAPIBadRequest(
                "Unrecognised signature: method=%s op=%s" % signature)
        else:
            return function(self, request, *args, **kwargs)

    @classmethod
    def decorate(cls, func):
        """Decorate all exported operations with the given function.

        Exports are stored in a class attribute. Calling this function
        replaces that attribute, with all the exported functions decorated
        with `decorate`. This can be called multiple times to add additional
        layers of decoration.

        :param func: A single-argument callable.
        """
        cls.exports = {
            name: func(export)
            for name, export in cls.exports.items()
        }
        # Now also decorate the anonymous handler, if present.
        if cls.anonymous is not None and bool(cls.anonymous):
            if issubclass(cls.anonymous, OperationsHandlerMixin):
                cls.anonymous.decorate(func)


class OperationsHandler(
        OperationsHandlerMixin, BaseHandler,
        metaclass=OperationsHandlerType):
    """Base handler that supports operation dispatch."""


class AnonymousOperationsHandler(
        OperationsHandlerMixin, AnonymousBaseHandler,
        metaclass=OperationsHandlerType):
    """Anonymous base handler that supports operation dispatch."""


def method_fields_reserved_fields_patch(self, handler, fields):
    """Return the field callables that map to a handler.

    Piston by default does not allow the ability to use names of fields
    that are the same as other class attributes.

    This overrides this ability and prefixes any `RESERVED_FIELDS` with "_"
    to allow handlers to still use that field.

    E.g. "model" classmethod on the `BlockDeviceHandler`.
    """
    if not handler:
        return {}
    ret = dict()
    for field in fields:
        field_method = field
        if field in Emitter.RESERVED_FIELDS:
            field_method = "_%s" % field_method
        t = getattr(handler, str(field_method), None)
        if t and callable(t):
            ret[field] = t
    return ret

Emitter.method_fields = method_fields_reserved_fields_patch
