from ..extern.six import string_types
from ..plugins import PluginBase

import numpy
from abc import abstractmethod, abstractproperty

def get_slice_size(start, stop, step):
    """
    Return the size of an array slice
    
    Parameters
    ----------
    start : int
        the beginning of the slice
    stop : int
        the end of the slice
    step : int
        the slice step size
    
    Returns
    -------
    N : int
        the total size of the slice
    """
    N, remainder = divmod(stop-start, step)
    if remainder: N += 1
    return N

class FileType(PluginBase):
    """
    Abstract base class representing a file object
    """ 
    required_attributes = ['size', 'dtype'] 
    
    @abstractmethod
    def read(self, columns, start, stop, step=1):
        """
        Read the specified column(s) over the given range,
        returning a structured numpy array

        Parameters
        ----------
        columns : str, list of str
            the name of the column(s) to return
        start : int
            the row integer to start reading at
        stop : int
            the row integer to stop reading at
        step : int, optional
            the step size to use when reading; default is 1

        Returns
        -------
        data : array_like
            a numpy structured array holding the requested data
        """
        pass
        
    @property
    def columns(self):
        """
        Returns the names of the columns in the file; this defaults
        to the named fields in the file's :attr:`dtype` attribute
        
        This will differ from the data type's named fields if
        a view of the file has been returned with :func:`asarray`
        """
        try:
            return self._columns
        except AttributeError:
            return list(self.dtype.names)
    
    @columns.setter
    def columns(self, val):
        self._columns = val
    
    @property
    def ncol(self):
        """
        The number of data columns in the file
        """
        return len(self.columns)
    
    @property
    def shape(self):
        """
        The shape of the file, which defaults to (`size`, )
        
        Multiple dimensions can be introduced into the shape if
        a view of the file has been returned with :func:`asarray`
        """
        try:
            return self._shape
        except AttributeError:
            return (self.size,)
    
    @shape.setter
    def shape(self, val):
        self._shape = val
    
    def __len__(self):
        return self.size
      
    def __iter__(self):
        return iter(self.keys())
    
    def __repr__(self):
        args = (self.__class__.__name__, self.ncol, self.shape)
        return "<%s with %d column(s) and shape %s>" %args
    
    def keys(self):
        """
        Aliased function to return :attr:`columns`
        """
        return list(self.columns)
            
    def __getitem__(self, s):
        """
        This function provides numpy-like array indexing
        
        It supports:
        
            1.  integer, slice-indexing similar to arrays
            2.  string indexing using column names in :func:`keys`
        
        .. note::
        
            If a single column is being returned, a numpy array 
            holding the data is returned, rather than a structured
            array with only a single field.
        """
        # dont call asarray unless we have a single string index
        asarray = False
        if isinstance(s, string_types): 
            s = [s]
            asarray = True
        
        # if index is a list, it should contain a series of column names
        # this will return a "view" of the file, slicing the data type
        # to include only the requested columns
        if isinstance(s, list):
            
            # must be a list of str
            if not all(isinstance(k, string_types) for k in s):
                raise IndexError("string keys should be one of %s" %str(self.keys()))
            
            # crash if the dtype has no fields
            if self.dtype.names is None:
                raise IndexError(("cannot access view of specific columns after `asarray()` " 
                                  "has been called; use integer array indexing instead"))
                
            # all strings must be valid column names
            if not all(ss in self.keys() for ss in s):
                invalid = [col for col in s if s not in self.keys()]
                raise IndexError("invalid string keys: %s; run keys() for valid options" %str(invalid))
            
            # create a new object, with slice of dtype
            obj = object.__new__(self.__class__)
            obj.dtype = numpy.dtype([(col, self.dtype[col]) for col in s])
            obj.size = self.size
            
            # set the owner of the underlying memory
            if getattr(self, 'base', None) is not None:
                obj.base = self.base
            else:
                obj.base = self
            
            # return the single numpy array if only a 
            # single column was asked for
            if len(s) == 1 and asarray: obj = obj.asarray()
            
            return obj
        
        # tuple for indices in multiple dimensions
        # this can either be of length 1 or 2
        second_axis_index = None
        if isinstance(s, tuple):
            
            # verify the tuple shape
            if len(s) > len(self.shape):
                args = len(self.shape), len(s)
                raise IndexError("file dimension is %d, but you supplied tuple of length %d" %args)
                
            if len(s) == 1: 
                s = s[0]
            elif len(s) == 2:
                s, second_axis_index = s
            else:
                raise IndexError("tuple index '%s' not understood" %str(s))
        
        # input is integer
        if isinstance(s, int):
            if s < 0: s += self.size
            start, stop, step = s, s+1, 1
        # input is a slice
        elif isinstance(s, slice):
            start, stop, step = s.indices(self.size)
        else:
            raise IndexError("index '%s' not understood - should be an integer or slice" %str(s))
        
        # call the read function over the desired row range
        # if we don't own memory, return from 'base' attribute
        if getattr(self, 'base', None) is None:
            toret = self.read(self.keys(), start, stop, step)
        else:
            toret = self.base.read(self.keys(), start, stop, step)
            
        # if file has no named fields, then 
        # try to view the output as a single numpy array
        if len(self.dtype) == 0:
            try:
                toret = toret.view(self.dtype)
                if len(self.shape) > 1:
                    toret = toret.reshape((-1, self.shape[1]))
            except Exception as e:
                raise ValueError("error trying to view slice as a single numpy array: %s" %str(e))
            
        # if we have an index for the second dimension
        # then slice the return value
        if second_axis_index is not None:
            toret = toret[:,second_axis_index]
            
        return toret
        
    def asarray(self):
        """
        Return a view of the file, where the fields of the 
        structured array are stacked in columns of a single
        numpy array
        
        Examples
        --------
        
        # original file has three named fields
        >> ff.dtype
        dtype([('ra', '<f4'), ('dec', '<f4'), ('z', '<f4')])
        >> ff.shape
        (1000,)
        >> ff.columns
        ['ra', 'dec', 'z']
        >> ff[:3]
        array([(235.63442993164062, 59.39099884033203, 0.6225500106811523),
               (140.36181640625, -1.162310004234314, 0.5026500225067139),
               (129.96627807617188, 45.970130920410156, 0.4990200102329254)],
              dtype=(numpy.record, [('ra', '<f4'), ('dec', '<f4'), ('z', '<f4')]))
        
        # select subset of columns and switch the ordering
        # and convert output to a single numpy array
        >> x = ff[['dec', 'ra']].asarray()
        >> x.dtype
        dtype('float32')
        >> x.shape
        (1000, 2)
        >> x.columns
        ['dec', 'ra']
        >> x[:3]
        array([[  59.39099884,  235.63442993],
               [  -1.16231   ,  140.36181641],
               [  45.97013092,  129.96627808]], dtype=float32)
        
        # select only the first column (dec)
        >> dec = x[:,0]
        >> dec[:3]
        array([ 59.39099884,  -1.16231   ,  45.97013092], dtype=float32)
        

        Returns
        -------
        FileType : 
            a file object that will return a numpy array with 
            the columns representing the fields
        """
        # no named fields --> crash
        if not len(self.dtype):
            raise ValueError("no named dtype fields to convert to numpy array")
        
        # multiple vector dtypes --> crash
        if len(self.dtype) > 1 and any(len(self.dtype[col].shape) for col in self.dtype.names):
            raise ValueError("cannot convert multiple vector data types to numpy array")
            
        # different dtypes --> crash
        if any(self.dtype[col].base != self.dtype[0].base for col in self.dtype.names):
            raise ValueError("cannot convert data types of different types to single numpy array")
        
        # create the new object
        obj = object.__new__(self.__class__)
        
        # the second axis of the shape
        if len(self.dtype) == 1:
            subshape = self.dtype[0].shape
        else:
            subshape = (len(self.dtype),)
    
        obj.dtype   = self.dtype[0].base
        obj.columns = list(self)
        obj.shape   = (self.size, ) + subshape
        obj.size    = self.size
        if getattr(self, 'base', None) is not None:
            obj.base = self.base
        else:
            obj.base = self
           
        return obj
        

def io_extension_points():
    """
    Return a dictionary of the extension points for :mod:`io`
    
    This returns only the :class:`FileType` class
    """
    return {'FileType' : FileType}
