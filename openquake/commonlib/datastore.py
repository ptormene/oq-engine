#  -*- coding: utf-8 -*-
#  vim: tabstop=4 shiftwidth=4 softtabstop=4

#  Copyright (c) 2015, GEM Foundation

#  OpenQuake is free software: you can redistribute it and/or modify it
#  under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  OpenQuake is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU Affero General Public License
#  along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
import shutil
import cPickle
import collections
import numpy

try:
    import h5py
except ImportError:
    class mock_h5py(object):
        def __getattr__(self, name):
            raise ImportError('Could not import h5py.%s' % name)
    h5py = mock_h5py()

from openquake.commonlib.writers import write_csv


DATADIR = os.environ.get('OQ_DATADIR', os.path.expanduser('~/oqdata'))


def get_last_calc_id(datadir=DATADIR):
    """
    Extract the latest calculation ID from the given directory.
    If none is found, return 0.
    """
    calcs = [f for f in os.listdir(DATADIR) if re.match('calc_\d+', f)]
    if not calcs:
        return 0
    calc_ids = [int(calc[5:]) for calc in calcs]  # strip calc_
    return max(calc_ids)


def key2str(key):
    """
    Convert the key (a string or a tuple of strings) into a dash-separated
    ASCII string.
    """
    if isinstance(key, basestring):
        if '-' in key:
            raise KeyError('The key %s is invalid since it contains a dash'
                           % key)
        return str(key)
    return '-'.join(key)


def str2key(keystr):
    """
    Convert a key string into a tuple of strings, by splitting on dashes
    """
    return tuple(keystr.split('-'))


class DataStore(collections.MutableMapping):
    """
    DataStore class to store the inputs/outputs of each calculation on the
    filesystem. It works like a mapping; composite keys ending with
    "h5" are associated to .hdf5 files; other keys are associated
    to .pik files containing pickled objects.

    NB: the calc_dir is created only at the first attempt to write on it,
    so there is potentially a race condition if the client code does not pass
    an unique calc_id and relies on the DataStore to create it.

    Here is a minimal example of usage:

    >>> ds = DataStore()
    >>> ds['example'] = 'hello world'
    >>> ds.items()
    [(('example',), 'hello world')]
    >>> ds.clear()

    It is also possible to store callables with two arguments (key, datastore).
    They will be automatically invoked when the key is accessed.

    It possible to store numpy arrays in HDF5 format, if the library h5py is
    installed and if the last field of the key is 'h5'. It is also possible
    to store items of the form (name, value) where name is a string and value
    is an array, and the last field of the key is 'hdf5'. When reading the
    items, the DataStore will return a generator. The items will be ordered
    lexicographically according to their name.
    """
    def __init__(self, calc_id=None, datadir=DATADIR):
        if not os.path.exists(datadir):
            os.makedirs(datadir)
        if calc_id is None:  # use a new datastore
            self.calc_id = get_last_calc_id(datadir) + 1
        elif calc_id == -1:  # use the last datastore
            self.calc_id = get_last_calc_id(datadir)
        else:  # use the given datastore
            self.calc_id = calc_id
        self.calc_dir = os.path.join(datadir, 'calc_%s' % self.calc_id)
        if not os.path.exists(self.calc_dir):
            os.mkdir(self.calc_dir)
        self.export_dir = '.'

    def path(self, key):
        """
        Return the full path name associated to the given key
        """
        if len(key) > 1 and key[-1] in ('h5', 'hdf5'):
            fname = key2str(key[:-1]) + '.' + key[-1]
            return os.path.join(self.calc_dir, fname)
        return os.path.join(self.calc_dir, key2str(key) + '.pik')

    def export_path(self, key_fmt):
        """
        Return the name of the exported file.

        :param key_fmt: the datastore key plus the export format extension
        """
        assert len(key_fmt) >= 2, key_fmt
        fname, _ext = os.path.splitext(self.path(key_fmt[:-1]))
        basename = os.path.basename(fname) + '.' + key_fmt[-1]
        return os.path.join(self.export_dir, basename)

    def export_csv(self, key):
        """
        Generic csv exporter
        """
        dest = self.export_path(key + ('csv',))
        return write_csv(dest, self[key])

    def clear(self):
        """Remove the datastore from the file system"""
        shutil.rmtree(self.calc_dir)

    def getsize(self, *key):
        """
        Return the size in byte of the file associated to the given key.
        If no key is given, returns the total size of all files.
        """
        if key:
            return os.path.getsize(self.path(key))
        return sum(os.path.getsize(self.path(key)) for key in self)

    def get(self, key, default):
        """
        :returns: the value associated to the datastore key, or the default
        """
        try:
            return self[key]
        except IOError:
            return default

    def h5file(self, *key):
        """
        Extracts the HDF5 file underlying the given key.
        """
        if key[-1] not in ('h5', 'hdf5'):
            raise ValueError('Not an hf5 key: %s' % str(key))
        path = self.path(key)
        mode = 'r+' if os.path.exists(path) else 'w'
        return h5py.File(path, mode, libver='latest')

    def __getitem__(self, key):
        if key[-1] == 'h5':
            _dset, data = next(self._get_hdf5_items(key))
            return data
        elif key[-1] == 'hdf5':
            return self._get_hdf5_items(key)
        with open(self.path(key)) as df:
            value = cPickle.load(df)
            if callable(value):
                return value(key, self)
            return value

    def _get_hdf5_items(self, key):
        with self.h5file(*key) as h5f:
            for dset, data in sorted(h5f.iteritems()):
                yield dset, data[:]

    def _set_hdf5_items(self, key, items):
        with self.h5file(*key) as h5f:
            for dset, data in items:
                h5f.create_dataset(dset, data=data)

    def __setitem__(self, key, value):
        if key[-1] == 'h5':
            if not isinstance(value, numpy.ndarray):
                raise ValueError('%r is not a numpy array' % value)
            self._set_hdf5_items(key, [('dset', value)])
        elif key[-1] == 'hdf5':
            self._set_hdf5_items(key, value)
        else:
            with open(self.path(key), 'w') as df:
                return cPickle.dump(value, df, cPickle.HIGHEST_PROTOCOL)

    def __delitem__(self, key):
        os.remove(self.path(key))

    def __iter__(self):
        for f in sorted(os.listdir(self.calc_dir)):
            if f.endswith('.pik'):
                yield str2key(f[:-4])
            elif f.endswith('.h5'):
                yield str2key(f[:-3]) + ('h5',)
            elif f.endswith('.hdf5'):
                yield str2key(f[:-5]) + ('hdf5',)

    def __contains__(self, key):
        return key in set(self)

    def __len__(self):
        return sum(1 for f in os.listdir(self.calc_dir)
                   if f.endswith(('.pik', '.hdf5')))

    def __repr__(self):
        return '<%s %d>' % (self.__class__.__name__, self.calc_id)


def persistent_attribute(name, *extras):
    """
    Persistent attributes are persisted to the datastore and cached. Modifications
    to mutable objects are not automagically persisted. If you have a huge object
    that does not fit in memory use the datastore directory (for instance, open
    a HDF5 file to create an empty array, then populate it). Notice that you can
    use any dict-like data structure in place of the datastore, provided you can
    set attributes on it. Here is an example:

    >>> class Datastore(dict):
    ...     "A fake datastore"

    >>> class Store(object):
    ...     a = persistent_attribute('a')
    ...     def __init__(self, a):
    ...         self.datastore = Datastore()
    ...         self.a = a  # this assegnation will store the attribute

    >>> store = Store([1])
    >>> store.a  # this retrieves the attribute
    [1]
    >>> store.a.append(2)
    >>> store.a = store.a  # remember to store the modified attribute!

    :param name: the name of the attribute to be made persistent
    :param extras: strings to specify the underlying key in the datastore
    :returns: a property to be added to a class with a .datastore attribute
    """
    key = (name,) + extras
    privatekey = '_' + '_'.join(key)

    def getter(self):
        # Try to get the value from the privatekey attribute (i.e. from
        # the cache of the datastore); if not possible, get the value
        # from the datastore and set the cache; if not possible, get the
        # value from the precalculator and set the cache. If the value cannot
        # be retrieved, raise an AttributeError.
        try:
            try:
                return getattr(self.datastore, privatekey)
            except AttributeError:
                value = self.datastore[key]
                setattr(self.datastore, privatekey, value)
                return value
        except IOError:
            if self.precalc:
                try:
                    return getattr(self.precalc, name)
                except AttributeError:
                    value = self.datastore[key]
                    setattr(self.datastore, privatekey, value)
            else:
                raise AttributeError('_'.join(key))

    def setter(self, value):
        # Update the datastore and the private key
        self.datastore[key] = value
        setattr(self.datastore, privatekey, value)

    return property(getter, setter)
