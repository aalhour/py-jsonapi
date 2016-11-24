#!/usr/bin/env python3

# The MIT License (MIT)
#
# Copyright (c) 2016 Benedikt Schmitt
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
jsonapi.includer
================

:seealso: http://jsonapi.org/format/#fetching-includes

The :class:`Includer` helps to implement the JSON API *include* query
parameter, which lets the server include related resources into the response.

If fully implemented, the includer can also validate include paths and check
if they exist, before the related resources are loaded from the database.

Here is a short example:

.. code-block:: python3

    class ArticleIncluder(Includer):
        resource_class = Article

        author = ToOneRelationship(remote_types=["User"])
        comments = ToManyRelationship(remote_types=["Comment"])

The example above is equivalent to:

.. code-block:: python3

    class ArticleIncluder(Includer):
        resource_class = Article

        @ToOneRelationship(remote_types=["User"])
        def author(self, article, request):
            return article.author

        @ToManyRelationship(remote_types=["Comment"])
        def comments(self, article, request):
            return article.comments

The *remote_types* parameter allows the includer to follow and validate include
paths, before the inclusion is actually performed.

The includer methods must return the actual related resources and not only
their ids.

You can also subclass the includer and overridde some of its methods:

.. code-block:: python3

    class ArticleIncluder(Includer):

        def path_exists(self, path):
            if super().path_exists(path):
                return True
            # ...
            return False

        def fetch_paths(self, resources, paths, request):
            relatives = super().fetch_paths(resources, paths, request)
            # ....
            return relatives

        def fetch_resources(self, ids, request):
            pass
"""

# std
import logging
import types


__all__ = [
    "Relationship",
    "ToOneRelationship",
    "ToManyRelationship",
    "Includer"
]


LOG = logging.getLogger(__file__)


class Relationship(object):
    """
    A special method for the :class:`Includer`, which tells the includer,
    how to get the relatives from a resource.

    This class is the base :class:`ToOneRelationship` and
    :class:`ToManyRelationship`, never use it directly.

    :arg str name:
        The name of the encoded relationship (the JSON API name of the
        relationship).
    :arg str mapped_key:
        The name of the property on the resource class, which references the
        related resources.
    :arg callable fget:
        Receives a resource and returns the related resources.
    """

    #: True, if this is a to-one relationship.
    to_one = None

    #: True, if this is a to-many relationship
    to_many = None

    def __init__(
        self, name=None, mapped_key=None, fget=None, remote_types=None
        ):
        """
        """
        # This is an abstract class.
        assert type(self) is not Relationship

        #: The name of the relationship in the JSON API.
        self.name = name

        #: A set with the names of all remote types.
        self.remote_types = remote_types

        #: A method on an Includer, which receives a resource as argument
        #: and returns all related resources.
        self.fget = None
        if fget:
            self.getter(fget)

        #: The name of the relationship descriptor on the :class:`Includer`
        #: class, on which it has been defined.
        self.key = None

        #: The key on the resource class, which is mapped to this JSON API
        #: field.
        #: If None, we use :attr:`key`.
        self.mapped_key = mapped_key
        return None

    def __call__(self, fget):
        return self.getter(fget)

    def getter(self, fget):
        self.fget = fget
        self.name = self.name or fget.__name__
        return self

    def __get__(self, includer, owner):
        if includer is None:
            return self
        elif self.fget:
            return types.MethodType(self.fget, includer)
        else:
            return types.MethodType(self.default_get, includer)

    def default_get(self, includer, resource, request):
        return getattr(resource, self.mapped_key)

    def get(self, includer, resource, request):
        if self.fget:
            return self.fget(includer, resource, request)
        else:
            return self.default_get(includer, resource, request)


class ToOneRelationship(Relationship):
    """
    Returns the related resource or ``None`` in a *to-one* relationship.
    """

    #:
    to_one = True
    #:
    to_many = False


class ToManyRelationship(Relationship):
    """
    Returns the list of related resources.
    """

    #:
    to_one = False
    #:
    to_many = True


class Includer(object):
    """
    An includer tells the API how to fetch related resources. You can either
    overridde the special methods or you use the :class:`ToOneRelationship`
    and :class:`ToManyRelationship` decorators to implement an includer.

    :arg ~jsonapi.api.API api:
        The API, that owns this includer.
    """

    #: The resource class, which is associated with this includer.
    resource_class = None

    def __init__(self, api=None):
        """
        """
        self.__api = api

        self._relationships = dict()
        self._detect_includer_methods()
        return None

    def add_includer_method(self, key, method):
        """
        Adds a new includer method to the includer.

        :arg str key:
        :arg ~jsonapi.includer.Relationship method:
        """
        assert isinstance(method, (ToOneRelationship, ToManyRelationship))
        method.name = method.name or key
        method.mapped_key = method.mapped_key or key
        method.key = key
        self._relationships[method.name] = method
        return None

    def _detect_includer_methods(self):
        """
        Detects the :class:`ToOneRelationship` and :class:`ToManyRelationship`
        descriptors and adds them to an instance dictionary.
        """
        cls = type(self)
        for key in dir(cls):
            prop = getattr(cls, key)
            if not isinstance(prop, (ToOneRelationship, ToManyRelationship)):
                continue

            self.add_includer_method(key, prop)
        return None

    def get_descriptor(self, relname):
        """
        Returns the :class:`ToOneRelationship` or :class:`ToManyRelationship`
        descriptor for the relationship, if one exists and ``None`` otherwise.

        :arg str relname:
            The name of a relationship.
        """
        return self._relationships.get(relname)

    @property
    def api(self):
        """
        The :class:`~jsonapi.api.API`, whichs owns this includer.
        """
        return self.__api

    def init_api(self, api):
        """
        Called, when the includer is assigned to an API.

        :arg ~jsonapi.api.API api:
            The owning API
        """
        assert self.__api is None or self.__api is api
        self.__api = api
        return None

    def path_exists(self, path):
        """
        Checks, if the include path *path* exists.

        .. code-block:: python3

            includer.path_exists(["comments", "author"])

        :arg list path:
            A relationship path (list of relationship names)
        """
        if not path:
            return True

        name, *path = path
        relationship = self._relationships.get(name)
        if relationship is None:
            return False

        if relationship.remote_types is None:
            LOG.warning(
                "Can not check, if the include path '%s' exists, because the "
                "remote_types of the relationship '%s' on '%s' are not known.",
                ".".join(path), name, self
            )
            return True

        # Check recursive, if the remaining path is complete.
        for remote_type in relationship.remote_types:
            remote_includer = self.__api.get_includer(remote_type)
            if not remote_includer.path_exists(path):
                return False
        return True

    def paths_exist(self, paths):
        """
        Checks, if all include paths in *paths* exist.

        .. code-block:: python3

            includer.paths_exist([["author"], ["comments", "author"]])

        :arg list paths:
            A list of relationship paths.
        """
        return all(self.path_exists(path) for path in paths)

    def fetch_paths(self, resources, paths, request):
        """
        **Can be overridden.**

        Fetchs all resources in the include paths.

        :arg resources:
            A list of resources
        :arg list paths:
            A list of relationship paths
        :arg ~jsonapi.request.Request request:
            The current request context.
        """
        related = set()
        for path in paths:
            related.update(self.fetch_path(resources, path, request))
        return related

    def fetch_path(self, resources, path, request):
        """
        A helper method of :meth:`fetch_paths`, which only fetchs one path
        using the :class:`Relationship` descriptors.

        :arg resources:
            A list of resources
        :arg list path:
            A relationship path
        :arg ~jsonapi.request.Request request:
            The current request context.
        """
        name, *path = path
        relationship = self._relationships[name]

        related = set()
        if relationship.to_one:
            for resource in resources:
                related.add(relationship.get(self, resource, request))
            related.discard(None)
        else:
            for resource in resources:
                related.update(relationship.get(self, resource, request))
        return related

    def fetch_resources(self, ids, request):
        """
        **Must be overridden**

        Returns all resources with the given ids.`

        :arg list ids:
            A list of resource ids
        :arg ~jsonapi.request.Request request:
            The current request context.
        """
        raise NotImplementedError()
